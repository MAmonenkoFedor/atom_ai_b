from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils.text import get_valid_filename


def workspace_cabinet_upload_to(instance: "WorkspaceCabinetDocument", filename: str) -> str:
    safe = get_valid_filename(filename)
    return f"workspace_cabinet/{instance.user_id}/{uuid4().hex[:10]}_{safe}"


class WorkspaceCabinetDocument(models.Model):
    """Personal workspace documents for the employee cabinet (uploads + external links)."""

    class Source(models.TextChoices):
        UPLOAD = "upload", "Upload"
        EXTERNAL = "external", "External link"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workspace_cabinet_documents",
    )
    title = models.CharField(max_length=500)
    document_type = models.CharField(max_length=16)
    source = models.CharField(max_length=16, choices=Source.choices)
    external_href = models.TextField(blank=True)
    file = models.FileField(upload_to=workspace_cabinet_upload_to, blank=True, null=True)
    storage_provider = models.ForeignKey(
        "storage.StorageProvider",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="workspace_cabinet_documents",
    )
    storage_object_key = models.TextField(blank=True, default="")
    upload_stored_bytes = models.PositiveBigIntegerField(default=0)
    owner_label = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self) -> str:
        return f"{self.user_id}:{self.title[:40]}"

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
        return (self.external_href or "").strip()

    def to_api_dict(self, request) -> dict:
        return {
            "id": f"doc-{self.pk}",
            "title": self.title,
            "type": self.document_type,
            "updated_at": self.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "owner": self.owner_label,
            "href": self.resolve_href(request),
        }
