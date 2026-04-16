from django.conf import settings
from django.db import models


class Chat(models.Model):
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
    )
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
