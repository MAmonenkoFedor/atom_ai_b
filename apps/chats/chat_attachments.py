"""Загрузка и выдача вложений чата (S3 / локальный FileField)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from django.shortcuts import get_object_or_404
from django.utils.text import get_valid_filename
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.chats.models import Chat, ChatAttachment
from apps.storage.credentials_vault import decrypt_credentials_field
from apps.storage.enforcement import assert_chat_upload_allowed
from apps.storage.router import get_default_object_storage_provider
from apps.storage import s3_runtime

_ALLOWED_SUFFIXES = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".csv",
        ".txt",
        ".md",
        ".json",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".ppt",
        ".pptx",
    }
)


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


def list_chat_attachments(request, chat: Chat) -> list[dict]:
    qs = ChatAttachment.objects.filter(chat=chat).select_related("uploaded_by", "storage_provider")
    return [obj.to_api_dict(request) for obj in qs]


def create_chat_attachment_upload(request, chat: Chat, upload) -> dict:
    name = get_valid_filename(upload.name)
    suffix = Path(name).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise ValidationError({"file": "Unsupported file type."})
    size = int(getattr(upload, "size", None) or 0)
    if size > 15 * 1024 * 1024:
        raise ValidationError({"file": "File too large (max 15MB)."})

    project = getattr(chat, "project", None)
    org_id = getattr(project, "organization_id", None) if project is not None else None
    assert_chat_upload_allowed(
        user_id=request.user.id,
        chat_project_id=project.pk if project is not None else None,
        chat_organization_id=org_id,
        incoming_bytes=size,
    )

    owner = _owner_label_for_user(request.user)
    mime_type = (getattr(upload, "content_type", None) or "").strip() or "application/octet-stream"

    provider = get_default_object_storage_provider()
    if provider:
        object_key = f"chat_attachments/{chat.id}/{uuid4().hex[:10]}_{name}"
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
                content_type=mime_type,
            )
        except Exception as exc:
            raise ValidationError(
                {"file": f"Не удалось сохранить файл в объектном хранилище: {exc}"},
            ) from exc
        obj = ChatAttachment.objects.create(
            chat=chat,
            uploaded_by=request.user,
            title=name,
            document_type=_infer_document_type(name),
            source=ChatAttachment.Source.UPLOAD,
            storage_provider=provider,
            storage_object_key=object_key,
            upload_stored_bytes=len(body),
            mime_type=mime_type,
        )
        return obj.to_api_dict(request)

    obj = ChatAttachment(
        chat=chat,
        uploaded_by=request.user,
        title=name,
        document_type=_infer_document_type(name),
        source=ChatAttachment.Source.UPLOAD,
        mime_type=mime_type,
    )
    obj.file.save(name, upload, save=True)
    obj.refresh_from_db()
    if obj.file:
        sz = int(obj.file.size or 0)
        if sz:
            obj.upload_stored_bytes = sz
            obj.save(update_fields=["upload_stored_bytes"])
    return obj.to_api_dict(request)


def delete_chat_attachment(request, chat: Chat, attachment_id: int) -> None:
    obj = get_object_or_404(
        ChatAttachment.objects.select_related("storage_provider"),
        pk=attachment_id,
        chat_id=chat.pk,
    )
    if chat.created_by_id == request.user.id:
        pass
    elif obj.uploaded_by_id == request.user.id:
        pass
    else:
        raise PermissionDenied("Only the uploader or chat owner can delete this attachment.")

    key = (obj.storage_object_key or "").strip()
    if key and obj.storage_provider_id:
        prov = obj.storage_provider
        if prov:
            creds = decrypt_credentials_field(prov.credentials)
            try:
                if creds.get("access_key") and creds.get("secret_key"):
                    s3_runtime.delete_object(
                        prov,
                        access_key=creds["access_key"],
                        secret_key=creds["secret_key"],
                        object_key=key,
                    )
            except Exception:
                pass
    if obj.file:
        obj.file.delete(save=False)
    obj.delete()
