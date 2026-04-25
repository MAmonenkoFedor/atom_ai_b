"""Encrypt storage provider credentials at rest (Fernet)."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from django.conf import settings


def _fernet_key_bytes() -> bytes:
    raw = (getattr(settings, "STORAGE_CREDENTIALS_FERNET_KEY", "") or "").strip()
    if raw:
        return raw.encode("utf-8") if isinstance(raw, str) else raw
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet():
    from cryptography.fernet import Fernet

    return Fernet(_fernet_key_bytes())


def credentials_blob_has_secret(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    if raw.get("v") == 1 and isinstance(raw.get("ct"), str) and raw["ct"].strip():
        return True
    return bool((raw.get("secret_key") or "").strip())


def decrypt_credentials_field(raw: Any) -> dict[str, str]:
    """Return ``access_key`` / ``secret_key`` strings (possibly empty). Supports legacy plaintext."""
    if not isinstance(raw, dict):
        return {"access_key": "", "secret_key": ""}
    if raw.get("v") == 1 and isinstance(raw.get("ct"), str) and raw["ct"].strip():
        try:
            plain = _fernet().decrypt(raw["ct"].encode("utf-8")).decode("utf-8")
            data = json.loads(plain)
            if isinstance(data, dict):
                return {
                    "access_key": str(data.get("access_key") or "").strip(),
                    "secret_key": str(data.get("secret_key") or "").strip(),
                }
        except Exception:
            return {"access_key": "", "secret_key": ""}
    return {
        "access_key": str(raw.get("access_key") or "").strip(),
        "secret_key": str(raw.get("secret_key") or "").strip(),
    }


def encrypt_credentials_field(access_key: str, secret_key: str) -> dict[str, Any]:
    payload = json.dumps(
        {"access_key": (access_key or "").strip(), "secret_key": (secret_key or "").strip()},
        separators=(",", ":"),
    )
    token = _fernet().encrypt(payload.encode("utf-8")).decode("utf-8")
    return {"v": 1, "ct": token}
