"""Human-readable ``source_label`` for storage quotas (stable UI contract)."""

from __future__ import annotations

from apps.storage.models import StorageQuota


def build_storage_quota_source_label(scope: str, scope_id: str) -> str:
    """
    Short label for UI, e.g. «Платформа», «Организация: Acme», «Проект: Mobile App».
    """
    sid = (scope_id or "").strip()

    if scope == StorageQuota.Scope.GLOBAL:
        return "Платформа"

    if scope == StorageQuota.Scope.USER:
        if sid.isdigit():
            try:
                from django.contrib.auth import get_user_model

                User = get_user_model()
                u = User.objects.filter(pk=int(sid)).only("username", "first_name", "last_name", "email").first()
                if u:
                    name = (u.get_full_name() or "").strip() or (u.username or "").strip() or u.email
                    return f"Пользователь: {name}"
            except (ValueError, TypeError):
                pass
        return "Пользователь"

    if scope == StorageQuota.Scope.ORGANIZATION:
        if sid.isdigit():
            try:
                from apps.organizations.models import Organization

                org = Organization.objects.filter(pk=int(sid)).only("name").first()
                if org and org.name:
                    return f"Организация: {org.name}"
            except (ValueError, TypeError):
                pass
        return f"Организация (ID {sid})" if sid else "Организация"

    if scope == StorageQuota.Scope.PROJECT:
        if sid.isdigit():
            try:
                from apps.projects.models import Project

                proj = Project.objects.filter(pk=int(sid)).only("name").first()
                if proj and proj.name:
                    return f"Проект: {proj.name}"
            except (ValueError, TypeError):
                pass
        return f"Проект (ID {sid})" if sid else "Проект"

    return sid or scope
