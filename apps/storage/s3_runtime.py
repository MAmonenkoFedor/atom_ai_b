"""S3-compatible put/get used by document uploads (MinIO, AWS, …)."""

from __future__ import annotations

import logging
import mimetypes
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

# Shown to API clients; never interpolate raw boto/botocore exceptions into this.
OBJECT_STORAGE_UPLOAD_FAILED_USER_MESSAGE = (
    "Не удалось сохранить файл в объектном хранилище. Попробуйте позже."
)


def log_object_storage_upload_failure(exc: BaseException, context: str) -> None:
    logger.warning("object_storage upload failed context=%s", context, exc_info=exc)

if TYPE_CHECKING:
    from apps.storage.models import StorageProvider


def _client_for(provider: "StorageProvider", access_key: str, secret_key: str):
    import boto3
    from botocore.config import Config

    addressing_style = "path" if provider.path_style else "virtual"
    bcfg = Config(
        signature_version="s3v4",
        s3={"addressing_style": addressing_style},
        connect_timeout=30,
        read_timeout=120,
    )
    kw: dict = {
        "service_name": "s3",
        "aws_access_key_id": access_key,
        "aws_secret_access_key": secret_key,
        "config": bcfg,
        "use_ssl": provider.use_ssl,
    }
    ep = (provider.endpoint_url or "").strip()
    if ep:
        kw["endpoint_url"] = ep
    reg = (provider.region or "").strip()
    if reg:
        kw["region_name"] = reg
    return boto3.client(**kw)


def put_object_bytes(
    provider: "StorageProvider",
    *,
    access_key: str,
    secret_key: str,
    object_key: str,
    body: bytes,
    content_type: str | None = None,
) -> None:
    client = _client_for(provider, access_key, secret_key)
    extra: dict = {}
    ct = content_type or mimetypes.guess_type(object_key)[0] or "application/octet-stream"
    extra["ContentType"] = ct
    client.put_object(Bucket=provider.bucket, Key=object_key, Body=body, **extra)


class _CountingReader:
    def __init__(self, fileobj, max_bytes: int | None = None):
        self._fileobj = fileobj
        self._max_bytes = max_bytes
        self.bytes_read = 0

    def read(self, size: int = -1):
        chunk = self._fileobj.read(size)
        if not chunk:
            return chunk
        self.bytes_read += len(chunk)
        if self._max_bytes is not None and self.bytes_read > self._max_bytes:
            raise ValueError("File too large (max 15MB).")
        return chunk


def put_object_fileobj(
    provider: "StorageProvider",
    *,
    access_key: str,
    secret_key: str,
    object_key: str,
    fileobj,
    content_type: str | None = None,
    max_bytes: int | None = None,
) -> int:
    client = _client_for(provider, access_key, secret_key)
    ct = content_type or mimetypes.guess_type(object_key)[0] or "application/octet-stream"
    wrapped = _CountingReader(fileobj, max_bytes=max_bytes)
    client.upload_fileobj(
        Fileobj=wrapped,
        Bucket=provider.bucket,
        Key=object_key,
        ExtraArgs={"ContentType": ct},
    )
    return wrapped.bytes_read


def presigned_get_url(
    provider: "StorageProvider",
    *,
    access_key: str,
    secret_key: str,
    object_key: str,
    expires_in: int = 3600,
) -> str:
    client = _client_for(provider, access_key, secret_key)
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": provider.bucket, "Key": object_key},
        ExpiresIn=expires_in,
    )


def delete_object(
    provider: "StorageProvider",
    *,
    access_key: str,
    secret_key: str,
    object_key: str,
) -> None:
    client = _client_for(provider, access_key, secret_key)
    client.delete_object(Bucket=provider.bucket, Key=object_key)
