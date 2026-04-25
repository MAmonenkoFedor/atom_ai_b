"""S3-compatible connectivity check (MinIO, AWS, etc.)."""

from __future__ import annotations

import time
from typing import Any


def probe_s3_compatible_storage(
    *,
    endpoint_url: str | None,
    bucket: str,
    region: str | None,
    use_ssl: bool,
    path_style: bool,
    access_key: str,
    secret_key: str,
    timeout_seconds: float = 8.0,
) -> dict[str, Any]:
    """
    Returns ``{"ok": bool, "latency_ms": int, "message": str}``.
    Does not log secrets. Imports boto3/botocore lazily.
    """
    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import BotoCoreError, ClientError
    except ModuleNotFoundError as exc:
        return {
            "ok": False,
            "latency_ms": 0,
            "message": f"boto3 is required for storage probe: {exc}",
        }

    bucket = (bucket or "").strip()
    access_key = (access_key or "").strip()
    secret_key = (secret_key or "").strip()
    if not bucket:
        return {"ok": False, "latency_ms": 0, "message": "Bucket is required."}
    if not access_key or not secret_key:
        return {"ok": False, "latency_ms": 0, "message": "Access key and secret key are required."}

    ep = (endpoint_url or "").strip() or None
    reg = (region or "").strip() or None

    addressing_style = "path" if path_style else "virtual"
    bcfg = Config(
        signature_version="s3v4",
        s3={"addressing_style": addressing_style},
        connect_timeout=int(timeout_seconds),
        read_timeout=int(timeout_seconds),
    )

    session_kw: dict[str, Any] = {
        "aws_access_key_id": access_key,
        "aws_secret_access_key": secret_key,
        "config": bcfg,
    }
    if reg:
        session_kw["region_name"] = reg

    client_kw: dict[str, Any] = {
        "service_name": "s3",
        "use_ssl": use_ssl,
        **session_kw,
    }
    if ep:
        client_kw["endpoint_url"] = ep

    started = time.perf_counter()
    try:
        client = boto3.client(**client_kw)
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        code = (exc.response.get("Error") or {}).get("Code") or "ClientError"
        return {"ok": False, "latency_ms": latency_ms, "message": f"{code}: {exc}"}
    except BotoCoreError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {"ok": False, "latency_ms": latency_ms, "message": str(exc)}
    except Exception as exc:  # noqa: BLE001 — surface unexpected probe failures
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {"ok": False, "latency_ms": latency_ms, "message": str(exc)}

    latency_ms = int((time.perf_counter() - started) * 1000)
    return {"ok": True, "latency_ms": latency_ms, "message": "HeadBucket succeeded."}
