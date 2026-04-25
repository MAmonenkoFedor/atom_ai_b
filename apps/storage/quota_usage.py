"""Bytes used per quota scope (shared by serializers and enforcement)."""

from __future__ import annotations

from apps.storage.models import StorageQuota


def usage_bytes_for_quota(quota: StorageQuota, usage: dict) -> int:
    """Return current usage in bytes for the scope represented by ``quota``."""
    total = int(usage.get("total_bytes") or 0)

    if quota.scope == StorageQuota.Scope.GLOBAL and (quota.scope_id or "") == "":
        return total

    if quota.scope == StorageQuota.Scope.USER and (quota.scope_id or "").strip():
        uid = int(quota.scope_id)
        for row in usage.get("by_user", []):
            if int(row["user_id"]) == uid:
                return int(row["bytes"])
        return 0

    if quota.scope == StorageQuota.Scope.PROJECT and (quota.scope_id or "").strip():
        pid = int(quota.scope_id)
        for row in usage.get("by_project", []):
            if int(row["project_id"]) == pid:
                return int(row["bytes"])
        return 0

    if quota.scope == StorageQuota.Scope.ORGANIZATION and (quota.scope_id or "").strip():
        oid = int(quota.scope_id)
        for row in usage.get("by_organization", []):
            if int(row["organization_id"]) == oid:
                return int(row["bytes"])
        return 0

    return 0
