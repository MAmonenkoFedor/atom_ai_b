"""Soft warnings when usage crosses ``warn_bytes`` on active quotas."""

from __future__ import annotations

from apps.organizations.models import OrganizationMember
from apps.projects.models import ProjectMember
from apps.storage.enforcement import effective_quota_description
from apps.storage.models import StorageQuota
from apps.storage.service import compute_storage_usage


def _bytes_for_user(usage: dict, user_id: int) -> int:
    for row in usage.get("by_user", []):
        if int(row["user_id"]) == user_id:
            return int(row["bytes"])
    return 0


def _bytes_for_project(usage: dict, project_id: int) -> int:
    for row in usage.get("by_project", []):
        if int(row["project_id"]) == project_id:
            return int(row["bytes"])
    return 0


def _bytes_for_org(usage: dict, org_id: int) -> int:
    for row in usage.get("by_organization", []):
        if int(row["organization_id"]) == org_id:
            return int(row["bytes"])
    return 0


def collect_storage_warnings_for_user(user) -> list[str]:
    """Human-readable RU strings for the workspace cabinet UI."""
    if not user or not user.is_authenticated:
        return []
    quotas = [q for q in StorageQuota.objects.filter(is_active=True) if q.warn_bytes]
    if not quotas:
        return []
    usage = compute_storage_usage()
    total = int(usage["total_bytes"])
    uid = int(user.pk)
    warnings: list[str] = []

    org_ids = set(
        OrganizationMember.objects.filter(user=user, is_active=True).values_list(
            "organization_id",
            flat=True,
        )
    )
    project_ids = set(
        ProjectMember.objects.filter(user=user, is_active=True).values_list("project_id", flat=True)
    )

    for q in quotas:
        warn = int(q.warn_bytes)
        if warn <= 0:
            continue
        src = effective_quota_description(q)

        if q.scope == StorageQuota.Scope.GLOBAL and q.scope_id == "":
            if total >= warn:
                warnings.append(
                    f"[Глобальная квота] {src} — сейчас {total} Б при пороге предупреждения {warn} Б. "
                    "Имеет смысл удалить неиспользуемые вложения."
                )
        elif q.scope == StorageQuota.Scope.USER and q.scope_id == str(uid):
            cur = _bytes_for_user(usage, uid)
            if cur >= warn:
                warnings.append(
                    f"[Квота пользователя] {src} — сейчас {cur} Б при пороге предупреждения {warn} Б."
                )
        elif q.scope == StorageQuota.Scope.ORGANIZATION and q.scope_id:
            try:
                oid = int(q.scope_id)
            except ValueError:
                continue
            if oid in org_ids:
                cur = _bytes_for_org(usage, oid)
                if cur >= warn:
                    warnings.append(
                        f"[Квота организации] {src} — сейчас {cur} Б при пороге предупреждения {warn} Б."
                    )
        elif q.scope == StorageQuota.Scope.PROJECT and q.scope_id:
            try:
                pid = int(q.scope_id)
            except ValueError:
                continue
            if pid in project_ids:
                cur = _bytes_for_project(usage, pid)
                if cur >= warn:
                    warnings.append(
                        f"[Квота проекта] {src} — сейчас {cur} Б при пороге предупреждения {warn} Б."
                    )

    # Dedupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def storage_backend_hint() -> str:
    """``s3`` if default object storage is usable, else ``local``."""
    from apps.storage.router import get_default_object_storage_provider

    return "s3" if get_default_object_storage_provider() else "local"
