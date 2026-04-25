# Generated manually for ChatAttachment

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils.text import get_valid_filename


def _chat_attachment_upload_to(instance, filename: str) -> str:
    safe = get_valid_filename(filename)
    return f"chat_attachments/{instance.chat_id}/{uuid.uuid4().hex[:10]}_{safe}"


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("chats", "0003_alter_chat_project"),
        ("storage", "0002_storageprovider"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=500)),
                ("document_type", models.CharField(max_length=16)),
                (
                    "source",
                    models.CharField(
                        choices=[("upload", "Upload")],
                        default="upload",
                        max_length=16,
                    ),
                ),
                (
                    "file",
                    models.FileField(blank=True, null=True, upload_to=_chat_attachment_upload_to),
                ),
                ("storage_object_key", models.TextField(blank=True, default="")),
                ("upload_stored_bytes", models.PositiveBigIntegerField(default=0)),
                ("mime_type", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "chat",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="chats.chat",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="uploaded_chat_attachments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "storage_provider",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="chat_attachments",
                        to="storage.storageprovider",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at", "-id"),
            },
        ),
    ]
