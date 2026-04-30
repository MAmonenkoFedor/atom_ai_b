"""DB-backed workspace cabinet documents (list, seed, create)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from django.utils.text import get_valid_filename
from rest_framework.exceptions import ValidationError

from apps.storage.credentials_vault import decrypt_credentials_field
from apps.storage.enforcement import assert_workspace_upload_allowed
from apps.storage.router import get_default_object_storage_provider
from apps.storage import s3_runtime
from apps.workspaces.models import WorkspaceCabinetDocument

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
    from apps.workspaces import data as workspace_data

    user = request.user
    employee_id = workspace_data.resolve_employee_id_for_username(user.username)
    qs = WorkspaceCabinetDocument.objects.filter(user=user).order_by("-updated_at")
    rows = list(qs)
    if not rows:
        rows = _seed_defaults_for_user(user, employee_id)
    return [obj.to_api_dict(request) for obj in rows]


def create_workspace_document_link(request, title: str, url: str) -> dict:
    from apps.workspaces import data as workspace_data

    user = request.user
    employee_id = workspace_data.resolve_employee_id_for_username(user.username)
    owner = _owner_label(employee_id)
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
    from apps.workspaces import data as workspace_data

    user = request.user
    employee_id = workspace_data.resolve_employee_id_for_username(user.username)
    owner = _owner_label(employee_id)

    name = get_valid_filename(upload.name)
    suffix = Path(name).suffix.lower()
    if suffix not in _ALLOWED_DOC_UPLOAD_SUFFIXES:
        raise ValidationError({"file": "Unsupported file type."})
    size = getattr(upload, "size", None) or 0
    if size > 15 * 1024 * 1024:
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
                max_bytes=15 * 1024 * 1024,
            )
        except Exception as exc:
            raise ValidationError(
                {"file": f"Не удалось сохранить файл в объектном хранилище: {exc}"},
            ) from exc
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
