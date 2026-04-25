"""End-to-end smoke for the access service.

Run as::

    .\\.venv\\Scripts\\python.exe manage.py shell -c "exec(open('scripts/access_smoke.py', encoding='utf8').read())"

Idempotent: cleans up grants/templates/users it created on each run.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.access import service as access_service
from apps.access.bridge import capabilities_from_access
from apps.access.models import (
    PermissionGrant,
    RoleTemplate,
    RoleTemplateAssignment,
)
from apps.access.resolver import (
    can_delegate,
    has_permission,
    list_effective_permissions,
)


User = get_user_model()


def _ensure_user(email: str, *, is_super: bool = False, is_company_admin: bool = False) -> User:
    user, _ = User.objects.get_or_create(
        email=email,
        defaults={
            "username": email.split("@")[0],
            "is_active": True,
        },
    )
    user.is_active = True
    if is_super:
        user.is_staff = True
        user.is_superuser = True
    user.save()
    return user


def _purge(user: User) -> None:
    PermissionGrant.objects.filter(employee=user).delete()
    RoleTemplateAssignment.objects.filter(employee=user).delete()


def main() -> None:
    print("=== access smoke ===")

    actor = _ensure_user("smoke-actor@atom.test", is_super=True)
    target = _ensure_user("smoke-target@atom.test")
    _purge(target)

    print("[1] grant project.assign_rights @ project:arena (use_and_delegate)")
    res1 = access_service.grant_permission(
        employee=target,
        permission_code="project.assign_rights",
        scope_type="project",
        scope_id="arena",
        grant_mode="use_and_delegate",
        granted_by=actor,
        note="smoke",
    )
    g1 = res1.grant
    assert g1.status == PermissionGrant.STATUS_ACTIVE
    assert has_permission(target, "project.assign_rights", "project", "arena")
    assert not has_permission(target, "project.assign_rights", "project", "olympus")
    assert can_delegate(target, "project.assign_rights", "project", "arena")
    print("    -> ok, has_permission(arena)=True, has_permission(olympus)=False")

    print("[2] grant rights.grant @ company:atom (use_only) -> bridge -> capabilities.manage")
    access_service.grant_permission(
        employee=target,
        permission_code="rights.grant",
        scope_type="company",
        scope_id="atom",
        grant_mode="use_only",
        granted_by=actor,
        note="smoke",
    )
    bridged = capabilities_from_access(target)
    assert "capabilities.manage" in bridged, bridged
    print(f"    -> bridged caps: {sorted(bridged)}")

    print("[3] assign role template employee_base")
    template = RoleTemplate.objects.get(code="employee_base")
    res3 = access_service.assign_role_template(
        employee=target,
        role_template=template,
        scope_type="company",
        scope_id="atom",
        assigned_by=actor,
        note="smoke",
    )
    assignment = res3.assignment
    assert assignment.is_active
    eff = list_effective_permissions(target)
    by_code = {p["permission_code"] for p in eff}
    print(f"    -> effective codes ({len(by_code)}): {sorted(by_code)[:8]}...")
    assert "ai.chat.use" in by_code or "docs.view" in by_code, by_code

    print("[4] revoke g1 (project.assign_rights)")
    access_service.revoke_permission(
        grant=g1,
        revoked_by=actor,
        note="smoke-revoke",
    )
    g1.refresh_from_db()
    assert g1.status == PermissionGrant.STATUS_REVOKED
    assert not has_permission(target, "project.assign_rights", "project", "arena")
    print("    -> revoked, has_permission(arena)=False")

    print("[5] cleanup")
    _purge(target)
    print("=== access smoke OK ===")


main()
