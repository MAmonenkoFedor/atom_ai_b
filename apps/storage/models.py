from __future__ import annotations

from django.db import models


class StorageQuota(models.Model):
    """Platform storage quota (MVP: DB-backed limits; enforcement hooks come next)."""

    class Scope(models.TextChoices):
        GLOBAL = "global", "Global"
        ORGANIZATION = "organization", "Organization"
        PROJECT = "project", "Project"
        USER = "user", "User"

    scope = models.CharField(max_length=32, choices=Scope.choices, default=Scope.GLOBAL)
    scope_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Empty for global; otherwise organization id, project id, or user id.",
    )
    source_label = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Stable UI label, e.g. «Платформа», «Организация: Acme» (not parsed from scope).",
    )
    max_bytes = models.PositiveBigIntegerField()
    warn_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("scope", "scope_id"),
                name="uniq_storage_quota_scope",
            )
        ]
        ordering = ("scope", "scope_id")

    def __str__(self) -> str:
        return f"{self.scope}:{self.scope_id or '*'}"


class StorageProvider(models.Model):
    """S3-compatible object storage endpoint (control plane; upload routing follows later)."""

    class Kind(models.TextChoices):
        S3_COMPAT = "s3_compat", "S3-compatible (MinIO / AWS / …)"

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=128)
    kind = models.CharField(max_length=32, choices=Kind.choices, default=Kind.S3_COMPAT)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    priority = models.IntegerField(default=100)
    endpoint_url = models.CharField(
        max_length=512,
        blank=True,
        help_text="e.g. http://localhost:9000 — empty uses AWS default for the region.",
    )
    bucket = models.CharField(max_length=255)
    region = models.CharField(max_length=64, blank=True)
    use_ssl = models.BooleanField(default=True)
    path_style = models.BooleanField(
        default=True,
        help_text="True for most MinIO installs (path-style addressing).",
    )
    credentials = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("priority", "code")
        constraints = [
            models.UniqueConstraint(
                fields=("is_default",),
                condition=models.Q(is_default=True),
                name="uniq_storage_provider_single_default",
            ),
        ]

    def __str__(self) -> str:
        return self.code
