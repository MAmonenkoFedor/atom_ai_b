"""Department (OrgUnit) documents — list, upload, links; mirrors project_documents patterns."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from django.utils.text import get_valid_filename
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.access.policies import resolve_access
from apps.orgstructure.models import OrgUnit, OrgUnitDocument
from apps.storage.credentials_vault import decrypt_credentials_field
from apps.storage.enforcement import assert_project_upload_allowed
from apps.storage.router import get_default_object_storage_provider
from apps.storage import s3_runtime

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


def _as_metadata_only(doc: dict) -> dict:
    row = dict(doc)
    row["href"] = ""
    return row


def _infer_document_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith((".csv", ".xls", ".xlsx")):
        return "sheet"
    return "doc"


def _owner_label_for_user(user) -> str:
    if not user:
        return ""
    full = (user.get_full_name() or "").strip()
    if full:
        return full.split()[0] if full else ""
    return (user.username or "").strip() or "User"


def list_department_documents(request, org_unit: OrgUnit) -> list[dict]:
    read_decision = resolve_access(
        user=request.user,
        action="document.read",
        scope_type="document",
        scope_id=str(org_unit.id),
        resource=org_unit,
    )
    if not read_decision.allowed:
        metadata_decision = resolve_access(
            user=request.user,
            action="document.view_metadata",
            scope_type="document",
            scope_id=str(org_unit.id),
            resource=org_unit,
        )
        if not metadata_decision.allowed:
            raise PermissionDenied("You do not have access to department documents.")
    qs = OrgUnitDocument.objects.filter(org_unit=org_unit).select_related("org_unit").order_by("-updated_at")
    rows = [obj.to_api_dict(request) for obj in qs]
    if read_decision.allowed:
        return rows
    return [_as_metadata_only(row) for row in rows]


def create_department_document_link(request, org_unit: OrgUnit, title: str, url: str) -> dict:
    decision = resolve_access(
        user=request.user,
        action="document.share",
        scope_type="document",
        scope_id=str(org_unit.id),
        resource=org_unit,
    )
    if not decision.allowed:
        raise PermissionDenied("You do not have permission to add links to department documents.")
    owner = _owner_label_for_user(request.user)
    obj = OrgUnitDocument.objects.create(
        org_unit=org_unit,
        uploaded_by=request.user,
        title=title.strip(),
        document_type="link",
        source=OrgUnitDocument.Source.EXTERNAL,
        external_href=url.strip(),
        owner_label=owner,
    )
    return obj.to_api_dict(request)


def create_department_document_upload(request, org_unit: OrgUnit, upload) -> dict:
    decision = resolve_access(
        user=request.user,
        action="document.upload",
        scope_type="document",
        scope_id=str(org_unit.id),
        resource=org_unit,
    )
    if not decision.allowed:
        raise PermissionDenied("You do not have permission to upload department documents.")
    owner = _owner_label_for_user(request.user)
    name = get_valid_filename(upload.name)
    suffix = Path(name).suffix.lower()
    if suffix not in _ALLOWED_DOC_UPLOAD_SUFFIXES:
        raise ValidationError({"file": "Unsupported file type."})
    size = getattr(upload, "size", None) or 0
    if size > 15 * 1024 * 1024:
        raise ValidationError({"file": "File too large (max 15MB)."})

    assert_project_upload_allowed(
        user_id=request.user.id,
        project_id=0,
        organization_id=getattr(org_unit, "organization_id", None),
        incoming_bytes=int(size),
    )

    provider = get_default_object_storage_provider()
    if provider:
        object_key = f"org_unit_documents/{org_unit.id}/{uuid4().hex[:10]}_{name}"
        try:
            body = upload.read()
        except Exception as exc:
            raise ValidationError({"file": "Не удалось прочитать файл для загрузки."}) from exc
        if len(body) > 15 * 1024 * 1024:
            raise ValidationError({"file": "File too large (max 15MB)."})
        creds = decrypt_credentials_field(provider.credentials)
        try:
            s3_runtime.put_object_bytes(
                provider,
                access_key=creds["access_key"],
                secret_key=creds["secret_key"],
                object_key=object_key,
                body=body,
            )
        except Exception as exc:
            s3_runtime.log_object_storage_upload_failure(exc, "org_unit_document_upload")
            raise ValidationError({"file": s3_runtime.OBJECT_STORAGE_UPLOAD_FAILED_USER_MESSAGE}) from exc
        obj = OrgUnitDocument.objects.create(
            org_unit=org_unit,
            uploaded_by=request.user,
            title=name,
            document_type=_infer_document_type(name),
            source=OrgUnitDocument.Source.UPLOAD,
            owner_label=owner,
            storage_provider=provider,
            storage_object_key=object_key,
            upload_stored_bytes=len(body),
        )
        return obj.to_api_dict(request)

    obj = OrgUnitDocument(
        org_unit=org_unit,
        uploaded_by=request.user,
        title=name,
        document_type=_infer_document_type(name),
        source=OrgUnitDocument.Source.UPLOAD,
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
