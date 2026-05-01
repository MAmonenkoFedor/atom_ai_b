"""DB-backed workspace cabinet documents (list, seed, create)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from django.utils.text import get_valid_filename
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.access.policies import resolve_access
from apps.storage.credentials_vault import decrypt_credentials_field
from apps.storage.enforcement import assert_workspace_upload_allowed
from apps.storage.router import get_default_object_storage_provider
from apps.storage import s3_runtime
from apps.workspaces.models import WorkspaceCabinetDocument

def _as_metadata_only(doc: dict) -> dict:
    row = dict(doc)
    row["href"] = ""
    return row


MAX_UPLOAD_BYTES = 15 * 1024 * 1024

_ALLOWED_DOC_UPLOAD_SUFFIXES = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".csv",
        ".txt",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".ppt",
        ".pptx",
    }
)

# Shown once per user when they have no rows yet (replaces in-memory seed).
_SEED_TEMPLATE: list[dict] = [
    {
        "title": "Marketing roadmap Q2",
        "type": "doc",
        "owner": "",
        "href": "",
    },
    {
        "title": "Q2 budget (Google Sheets)",
        "type": "sheet",
        "owner": "",
        "href": "https://docs.google.com/spreadsheets/",
    },
    {
        "title": "Общая папка — Google Drive",
        "type": "link",
        "owner": "Команда",
        "href": "https://drive.google.com/drive/my-drive",
    },
]


def _infer_document_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith((".csv", ".xls", ".xlsx")):
        return "sheet"
    return "doc"


def _owner_label(employee_id: str) -> str:
    # Local import: avoid circular import with data at module load.
    from apps.workspaces import data as workspace_data

    profile = workspace_data.EMPLOYEE_VERTICAL_DIRECTORY.get(employee_id) or {}
    header = profile.get("header") or {}
    return str(header.get("full_name") or "Employee")


def _resolve_owner_context(username: str) -> tuple[str, str]:
    """Resolve employee id and display label once per request path."""
    from apps.workspaces import data as workspace_data

    employee_id = workspace_data.resolve_employee_id_for_username(username)
    return employee_id, _owner_label(employee_id)


def _seed_defaults_for_user(user, employee_id: str) -> list[WorkspaceCabinetDocument]:
    owner = _owner_label(employee_id)
    rows = [
        WorkspaceCabinetDocument(
            user=user,
            title=row["title"],
            document_type=row["type"],
            source=WorkspaceCabinetDocument.Source.EXTERNAL,
            external_href=(row.get("href") or "").strip(),
            owner_label=(row.get("owner") or owner),
        )
        for row in _SEED_TEMPLATE
    ]
    return WorkspaceCabinetDocument.objects.bulk_create(rows)


def list_workspace_documents(request) -> list[dict]:
    user = request.user
    resource = SimpleNamespace(user_id=user.id, id=None)
    read_decision = resolve_access(
        user=user,
        action="document.read",
        scope_type="document",
        scope_id=str(user.id),
        resource=resource,
    )
    if not read_decision.allowed:
        metadata_decision = resolve_access(
            user=user,
            action="document.view_metadata",
            scope_type="document",
            scope_id=str(user.id),
            resource=resource,
        )
        if not metadata_decision.allowed:
            raise PermissionDenied("You do not have permission to view workspace documents.")

    employee_id, _ = _resolve_owner_context(user.username)
    qs = WorkspaceCabinetDocument.objects.filter(user=user).order_by("-updated_at")
    orm_rows = list(qs)
    if not orm_rows:
        orm_rows = _seed_defaults_for_user(user, employee_id)

    payloads = [obj.to_api_dict(request) for obj in orm_rows]
    if read_decision.allowed:
        return payloads
    return [_as_metadata_only(row) for row in payloads]


def create_workspace_document_link(request, title: str, url: str) -> dict:
    user = request.user
    decision = resolve_access(
        user=user,
        action="document.share",
        scope_type="document",
        scope_id=str(user.id),
        resource=SimpleNamespace(user_id=user.id, id=None),
    )
    if not decision.allowed:
        raise PermissionDenied("You do not have permission to create workspace document links.")
    _, owner = _resolve_owner_context(user.username)
    obj = WorkspaceCabinetDocument.objects.create(
        user=user,
        title=title.strip(),
        document_type="link",
        source=WorkspaceCabinetDocument.Source.EXTERNAL,
        external_href=url.strip(),
        owner_label=owner,
    )
    return obj.to_api_dict(request)


def create_workspace_document_upload(request, upload) -> dict:
    user = request.user
    decision = resolve_access(
        user=user,
        action="document.upload",
        scope_type="document",
        scope_id=str(user.id),
        resource=SimpleNamespace(user_id=user.id, id=None),
    )
    if not decision.allowed:
        raise PermissionDenied("You do not have permission to upload workspace documents.")
    _, owner = _resolve_owner_context(user.username)

    name = get_valid_filename(upload.name)
    if not name.strip():
        raise ValidationError({"file": "Invalid file name."})
    suffix = Path(name).suffix.lower()
    if suffix not in _ALLOWED_DOC_UPLOAD_SUFFIXES:
        raise ValidationError({"file": "Unsupported file type."})
    size = getattr(upload, "size", None) or 0
    if size > MAX_UPLOAD_BYTES:
        raise ValidationError({"file": "File too large (max 15MB)."})

    assert_workspace_upload_allowed(user_id=user.id, incoming_bytes=int(size))

    provider = get_default_object_storage_provider()
    if provider:
        object_key = f"workspace_cabinet/{user.id}/{uuid4().hex[:10]}_{name}"
        content_type = getattr(upload, "content_type", None) or None
        creds = decrypt_credentials_field(provider.credentials)
        try:
            fileobj = getattr(upload, "file", upload)
            if hasattr(fileobj, "seek"):
                fileobj.seek(0)
            uploaded_bytes = s3_runtime.put_object_fileobj(
                provider,
                access_key=creds["access_key"],
                secret_key=creds["secret_key"],
                object_key=object_key,
                fileobj=fileobj,
                content_type=content_type,
                max_bytes=MAX_UPLOAD_BYTES,
            )
        except ValueError as exc:
            if str(exc) == "File too large (max 15MB).":
                raise ValidationError({"file": "File too large (max 15MB)."}) from exc
            s3_runtime.log_object_storage_upload_failure(exc, "workspace_cabinet_upload")
            raise ValidationError({"file": s3_runtime.OBJECT_STORAGE_UPLOAD_FAILED_USER_MESSAGE}) from exc
        except Exception as exc:
            s3_runtime.log_object_storage_upload_failure(exc, "workspace_cabinet_upload")
            raise ValidationError({"file": s3_runtime.OBJECT_STORAGE_UPLOAD_FAILED_USER_MESSAGE}) from exc
        obj = WorkspaceCabinetDocument.objects.create(
            user=user,
            title=name,
            document_type=_infer_document_type(name),
            source=WorkspaceCabinetDocument.Source.UPLOAD,
            owner_label=owner,
            storage_provider=provider,
            storage_object_key=object_key,
            upload_stored_bytes=int(uploaded_bytes),
        )
        return obj.to_api_dict(request)

    obj = WorkspaceCabinetDocument(
        user=user,
        title=name,
        document_type=_infer_document_type(name),
        source=WorkspaceCabinetDocument.Source.UPLOAD,
        owner_label=owner,
    )
    obj.file.save(name, upload, save=True)
    obj.refresh_from_db()
    if obj.file:
        sz = int(obj.file.size or 0)
        if sz:
            obj.upload_stored_bytes = sz
            obj.save(update_fields=["upload_stored_bytes"])
    return obj.to_api_dict(request)
