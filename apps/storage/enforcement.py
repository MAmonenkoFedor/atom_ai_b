from __future__ import annotations

from rest_framework.exceptions import ErrorDetail, ValidationError

from apps.storage.models import StorageQuota
from apps.storage.quota_usage import usage_bytes_for_quota
from apps.storage.service import compute_storage_usage


def effective_quota_description(quota: StorageQuota) -> str:
    """RU: что именно ограничило загрузку (для UI и логов)."""
    sid = (quota.scope_id or "").strip()

    if quota.scope == StorageQuota.Scope.GLOBAL:
        return (
            "глобальная квота — суммарный объём всех загрузок в workspace и проектах на платформе "
            "(общий лимит для всей системы)"
        )
    if quota.scope == StorageQuota.Scope.USER:
        return "квота пользователя — личные загрузки в вашем workspace (не проектные файлы других команд)"
    if quota.scope == StorageQuota.Scope.ORGANIZATION:
        label = f"квота организации (ID {sid})" if sid else "квота организации"
        if sid.isdigit():
            try:
                from apps.organizations.models import Organization

                org = Organization.objects.filter(pk=int(sid)).only("name").first()
                if org and org.name:
                    label = f"квота организации «{org.name}» (ID {sid})"
            except (ValueError, TypeError):
                pass
        return label + " — файлы, загруженные в проекты этой организации"
    if quota.scope == StorageQuota.Scope.PROJECT:
        label = f"квота проекта (ID {sid})" if sid else "квота проекта"
        if sid.isdigit():
            try:
                from apps.projects.models import Project

                proj = Project.objects.filter(pk=int(sid)).only("name").first()
                if proj and proj.name:
                    label = f"квота проекта «{proj.name}» (ID {sid})"
            except (ValueError, TypeError):
                pass
        return label + " — все файлы, прикреплённые к этому проекту"
    return f"квота (scope={quota.scope})"


def _check_quota(quota: StorageQuota, current: int, incoming: int) -> None:
    if not quota.is_active:
        return
    if current + incoming > quota.max_bytes:
        after = current + incoming
        who = effective_quota_description(quota)
        sid = (quota.scope_id or "").strip()
        max_b = int(quota.max_bytes)
        remaining_now = max(0, max_b - current)
        remaining_after = max_b - after
        msg = (
            "Загрузка отклонена: сработало ограничение хранилища.\n"
            f"Источник лимита: {who}.\n"
            f"Сейчас в зоне этой квоты ≈{current} Б, лимит {max_b} Б; "
            f"с учётом файла получилось бы ≈{after} Б.\n"
            "Удалите старые вложения или обратитесь к администратору."
        )
        raise ValidationError(
            {
                "file": [ErrorDetail(msg, code="storage_quota_exceeded")],
                "code": "storage_quota_exceeded",
                "storage_quota": {
                    "scope": quota.scope,
                    "scope_id": sid or None,
                    "source_label": (quota.source_label or "").strip() or None,
                    "max_bytes": max_b,
                    "current_bytes": current,
                    "incoming_bytes": incoming,
                    "remaining_bytes": remaining_now,
                    "remaining_after_upload": remaining_after,
                },
            }
        )


def assert_workspace_upload_allowed(*, user_id: int, incoming_bytes: int) -> None:
    """Enforce quotas for personal workspace cabinet uploads."""
    if incoming_bytes <= 0:
        return
    quotas = list(StorageQuota.objects.filter(is_active=True))
    if not quotas:
        return
    usage = compute_storage_usage()

    for q in quotas:
        if q.scope == StorageQuota.Scope.GLOBAL and q.scope_id == "":
            _check_quota(q, usage_bytes_for_quota(q, usage), incoming_bytes)
        elif q.scope == StorageQuota.Scope.USER and q.scope_id == str(user_id):
            _check_quota(q, usage_bytes_for_quota(q, usage), incoming_bytes)


def assert_project_upload_allowed(
    *,
    user_id: int,
    project_id: int,
    organization_id: int | None,
    incoming_bytes: int,
) -> None:
    """Enforce quotas for project document uploads."""
    if incoming_bytes <= 0:
        return
    quotas = list(StorageQuota.objects.filter(is_active=True))
    if not quotas:
        return
    usage = compute_storage_usage()

    for q in quotas:
        if q.scope == StorageQuota.Scope.GLOBAL and q.scope_id == "":
            _check_quota(q, usage_bytes_for_quota(q, usage), incoming_bytes)
        elif q.scope == StorageQuota.Scope.USER and q.scope_id == str(user_id):
            _check_quota(q, usage_bytes_for_quota(q, usage), incoming_bytes)
        elif q.scope == StorageQuota.Scope.PROJECT and q.scope_id == str(project_id):
            _check_quota(q, usage_bytes_for_quota(q, usage), incoming_bytes)
        elif (
            q.scope == StorageQuota.Scope.ORGANIZATION
            and organization_id is not None
            and q.scope_id == str(organization_id)
        ):
            _check_quota(q, usage_bytes_for_quota(q, usage), incoming_bytes)


def assert_chat_upload_allowed(
    *,
    user_id: int,
    chat_project_id: int | None,
    chat_organization_id: int | None,
    incoming_bytes: int,
) -> None:
    """Квоты для вложений чата: привязан к проекту — как у документов проекта, иначе — как workspace."""
    if incoming_bytes <= 0:
        return
    if chat_project_id is not None:
        assert_project_upload_allowed(
            user_id=user_id,
            project_id=chat_project_id,
            organization_id=chat_organization_id,
            incoming_bytes=incoming_bytes,
        )
    else:
        assert_workspace_upload_allowed(user_id=user_id, incoming_bytes=incoming_bytes)
