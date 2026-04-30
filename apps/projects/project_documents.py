"""Список и создание документов проекта (загрузка + внешние ссылки)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from django.utils.text import get_valid_filename
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.access.policies import resolve_access
from apps.projects.models import Project, ProjectDocument, ProjectMember
from apps.storage.credentials_vault import decrypt_credentials_field
from apps.storage.enforcement import assert_project_upload_allowed
from apps.storage.router import get_default_object_storage_provider
from apps.storage import s3_runtime
from apps.projects.project_permissions import PROJECT_SCOPE

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


def can_access_project_documents(user, project: Project) -> bool:
    decision = resolve_access(
        user=user,
        action="document.read",
        scope_type="document",
        scope_id=str(project.id),
        resource=project,
    )
    return decision.allowed


def can_manage_project_documents(user, project: Project) -> bool:
    decision = resolve_access(
        user=user,
        action="document.upload",
        scope_type="document",
        scope_id=str(project.id),
        resource=project,
    )
    return decision.allowed


def list_project_documents_for_workspace(request) -> list[dict]:
    """Все документы проектов, где пользователь состоит в команде или имеет
    активный project-scoped grant (для карточки workspace).

    Это критично для консистентности: если пользователю выдан ``docs.view``
    или любое project-scoped право, проект уже виден в queryset и должен
    раскрываться в виджете документов.
    """

    user = request.user
    project_ids: set[int] = set(
        ProjectMember.objects.filter(user=user, is_active=True).values_list(
            "project_id",
            flat=True,
        )
    )

    try:
        from apps.access.models import PermissionGrant
    except Exception:
        PermissionGrant = None  # type: ignore[assignment]

    if PermissionGrant is not None:
        from django.db.models import Q
        from django.utils import timezone

        now = timezone.now()
        grant_ids = (
            PermissionGrant.objects.filter(
                employee=user,
                scope_type=PROJECT_SCOPE,
                status=PermissionGrant.STATUS_ACTIVE,
            )
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .values_list("scope_id", flat=True)
        )
        for raw in grant_ids:
            try:
                project_ids.add(int(raw))
            except (TypeError, ValueError):
                continue

    if not project_ids:
        return []
    qs = (
        ProjectDocument.objects.filter(project_id__in=project_ids)
        .select_related("project")
        .order_by("-updated_at")[:200]
    )
    rows: list[dict] = []
    for obj in qs:
        read_decision = resolve_access(
            user=request.user,
            action="document.read",
            scope_type="document",
            scope_id=str(obj.project_id),
            resource=obj.project,
        )
        if read_decision.allowed:
            rows.append(obj.to_api_dict(request))
            continue
        metadata_decision = resolve_access(
            user=request.user,
            action="document.view_metadata",
            scope_type="document",
            scope_id=str(obj.project_id),
            resource=obj.project,
        )
        if metadata_decision.allowed:
            rows.append(_as_metadata_only(obj.to_api_dict(request)))
    return rows


def list_project_documents(request, project: Project) -> list[dict]:
    read_decision = resolve_access(
        user=request.user,
        action="document.read",
        scope_type="document",
        scope_id=str(project.id),
        resource=project,
    )
    metadata_decision = None
    if not read_decision.allowed:
        metadata_decision = resolve_access(
            user=request.user,
            action="document.view_metadata",
            scope_type="document",
            scope_id=str(project.id),
            resource=project,
        )
        if not metadata_decision.allowed:
            raise PermissionDenied("You are not a member of this project.")
    qs = ProjectDocument.objects.filter(project=project).select_related("project").order_by("-updated_at")
    rows = [obj.to_api_dict(request) for obj in qs]
    if read_decision.allowed:
        return rows
    return [_as_metadata_only(row) for row in rows]


def create_project_document_link(request, project: Project, title: str, url: str) -> dict:
    decision = resolve_access(
        user=request.user,
        action="document.share",
        scope_type="document",
        scope_id=str(project.id),
        resource=project,
    )
    if not decision.allowed:
        raise PermissionDenied("Only project owner or editor can add documents.")
    owner = _owner_label_for_user(request.user)
    obj = ProjectDocument.objects.create(
        project=project,
        uploaded_by=request.user,
        title=title.strip(),
        document_type="link",
        source=ProjectDocument.Source.EXTERNAL,
        external_href=url.strip(),
        owner_label=owner,
    )
    return obj.to_api_dict(request)


def create_project_document_upload(request, project: Project, upload) -> dict:
    decision = resolve_access(
        user=request.user,
        action="document.upload",
        scope_type="document",
        scope_id=str(project.id),
        resource=project,
    )
    if not decision.allowed:
        raise PermissionDenied("Only project owner or editor can add documents.")
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
        project_id=project.id,
        organization_id=getattr(project, "organization_id", None),
        incoming_bytes=int(size),
    )

    provider = get_default_object_storage_provider()
    if provider:
        object_key = f"project_documents/{project.id}/{uuid4().hex[:10]}_{name}"
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
            raise ValidationError(
                {"file": f"Не удалось сохранить файл в объектном хранилище: {exc}"},
            ) from exc
        obj = ProjectDocument.objects.create(
            project=project,
            uploaded_by=request.user,
            title=name,
            document_type=_infer_document_type(name),
            source=ProjectDocument.Source.UPLOAD,
            owner_label=owner,
            storage_provider=provider,
            storage_object_key=object_key,
            upload_stored_bytes=len(body),
        )
        return obj.to_api_dict(request)

    obj = ProjectDocument(
        project=project,
        uploaded_by=request.user,
        title=name,
        document_type=_infer_document_type(name),
        source=ProjectDocument.Source.UPLOAD,
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
