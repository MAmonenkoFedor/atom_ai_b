from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils.text import get_valid_filename


def chat_attachment_upload_to(instance: "ChatAttachment", filename: str) -> str:
    safe = get_valid_filename(filename)
    return f"chat_attachments/{instance.chat_id}/{uuid4().hex[:10]}_{safe}"


class Chat(models.Model):
    SCOPE_PERSONAL = "personal"
    SCOPE_DEPARTMENT = "department"
    SCOPE_PROJECT = "project"
    SCOPE_CHOICES = (
        (SCOPE_PERSONAL, "Personal"),
        (SCOPE_DEPARTMENT, "Department"),
        (SCOPE_PROJECT, "Project"),
    )
    TYPE_GENERAL = "general"
    TYPE_PROJECT = "project"
    TYPE_CHOICES = (
        (TYPE_GENERAL, "General"),
        (TYPE_PROJECT, "Project"),
    )
    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = (
        (STATUS_OPEN, "Open"),
        (STATUS_CLOSED, "Closed"),
    )

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="chats",
        null=True,
        blank=True,
    )
    org_unit = models.ForeignKey(
        "orgstructure.OrgUnit",
        on_delete=models.CASCADE,
        related_name="chats",
        null=True,
        blank=True,
    )
    chat_type = models.CharField(max_length=32, choices=TYPE_CHOICES, default=TYPE_GENERAL)
    chat_scope = models.CharField(max_length=32, choices=SCOPE_CHOICES, default=SCOPE_PERSONAL)
    title = models.CharField(max_length=255)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_OPEN)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_chats",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.title


class ChatMember(models.Model):
    ROLE_OWNER = "owner"
    ROLE_MEMBER = "member"
    ROLE_CHOICES = (
        (ROLE_OWNER, "Owner"),
        (ROLE_MEMBER, "Member"),
    )

    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_memberships",
    )
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("chat", "user"),
                name="uniq_chat_member",
            )
        ]
        ordering = ("-joined_at",)

    def __str__(self) -> str:
        return f"{self.chat_id}:{self.user_id}:{self.role}"


class Message(models.Model):
    TYPE_USER = "user"
    TYPE_ASSISTANT = "assistant"
    TYPE_SYSTEM = "system"
    TYPE_CHOICES = (
        (TYPE_USER, "User"),
        (TYPE_ASSISTANT, "Assistant"),
        (TYPE_SYSTEM, "System"),
    )

    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="messages")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="messages",
        null=True,
        blank=True,
    )
    message_type = models.CharField(max_length=32, choices=TYPE_CHOICES, default=TYPE_USER)
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")

    def __str__(self) -> str:
        return f"{self.chat_id}:{self.message_type}:{self.id}"


class ChatAttachment(models.Model):
    """Файлы, прикреплённые к потоку чата (для контекста и скачивания)."""

    class Source(models.TextChoices):
        UPLOAD = "upload", "Upload"

    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_chat_attachments",
    )
    title = models.CharField(max_length=500)
    document_type = models.CharField(max_length=16)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.UPLOAD)
    file = models.FileField(upload_to=chat_attachment_upload_to, blank=True, null=True)
    storage_provider = models.ForeignKey(
        "storage.StorageProvider",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="chat_attachments",
    )
    storage_object_key = models.TextField(blank=True, default="")
    upload_stored_bytes = models.PositiveBigIntegerField(default=0)
    mime_type = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return f"{self.chat_id}:{self.title[:40]}"

    def resolve_href(self, request) -> str:
        key = (self.storage_object_key or "").strip()
        if key and self.storage_provider_id:
            from apps.storage.credentials_vault import decrypt_credentials_field
            from apps.storage.s3_runtime import presigned_get_url

            prov = self.storage_provider
            if prov:
                c = decrypt_credentials_field(prov.credentials)
                if c.get("access_key") and c.get("secret_key"):
                    return presigned_get_url(
                        prov,
                        access_key=c["access_key"],
                        secret_key=c["secret_key"],
                        object_key=key,
                    )
        if self.file:
            return request.build_absolute_uri(self.file.url)
        return ""

    def to_api_dict(self, request) -> dict:
        return {
            "id": f"catt-{self.pk}",
            "title": self.title,
            "type": self.document_type,
            "href": self.resolve_href(request),
            "size_bytes": int(self.upload_stored_bytes or 0),
            "mime_type": (self.mime_type or "").strip(),
            "updated_at": self.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "owner": (self.uploaded_by.get_username() if self.uploaded_by else "") or "",
            "chat_id": str(self.chat_id),
        }
