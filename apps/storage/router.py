"""Resolve default object-storage provider for runtime uploads."""

from __future__ import annotations

from apps.storage.credentials_vault import decrypt_credentials_field
from apps.storage.models import StorageProvider


def get_default_object_storage_provider() -> StorageProvider | None:
    """Active default S3-compatible provider with usable credentials and bucket."""
    qs = (
        StorageProvider.objects.filter(
            is_active=True,
            is_default=True,
            kind=StorageProvider.Kind.S3_COMPAT,
        )
        .order_by("priority", "code")
        .first()
    )
    if not qs:
        return None
    if not (qs.bucket or "").strip():
        return None
    creds = decrypt_credentials_field(qs.credentials)
    if not creds.get("access_key") or not creds.get("secret_key"):
        return None
    return qs
