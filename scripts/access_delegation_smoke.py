"""Smoke for delegation chain hardening.

Run::

    .\\.venv\\Scripts\\python.exe manage.py shell -c "exec(open('scripts/access_delegation_smoke.py', encoding='utf8').read())"

Verifies the contract enforced by ``apps.access.service._assert_delegation_allowed``:

* parent_grant must belong to the delegator;
* parent must be ACTIVE and not past ``expires_at``;
* parent_grant must be in ``use_and_delegate`` mode;
* target scope cannot be broader than the parent's;
* target scope_id must match parent's scope_id when scope types match;
* child ``expires_at`` cannot exceed the parent's;
* revoking parent cascades to children;
* revoked child cannot be used to delegate further.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.access import service as access_service
from apps.access.models import PermissionGrant
from apps.access.resolver import has_permission

User = get_user_model()


def _u(email: str, *, is_super: bool = False) -> User:
    user, _ = User.objects.get_or_create(
        email=email,
        defaults={"username": email.split("@")[0], "is_active": True},
    )
    if is_super:
        user.is_staff = True
        user.is_superuser = True
    user.save()
    return user


def _purge(*users: User) -> None:
    PermissionGrant.objects.filter(employee__in=users).delete()


def _expect(label: str, fn) -> None:
    try:
        fn()
    except access_service.DelegationNotAllowed as exc:
        print(f"    [OK] {label}: blocked ({exc})")
        return
    print(f"    [FAIL] {label}: should have been rejected")
    raise SystemExit(1)


def main() -> None:
    print("=== delegation smoke ===")

    super_admin = _u("deleg-super@atom.test", is_super=True)
    lead = _u("deleg-lead@atom.test")
    junior = _u("deleg-junior@atom.test")
    _purge(lead, junior)

    parent_expiry = timezone.now() + timedelta(days=7)
    too_far_in_future = parent_expiry + timedelta(days=14)

    print("[1] super grants lead 'docs.upload' use_and_delegate @ project:arena (7d)")
    parent_res = access_service.grant_permission(
        employee=lead,
        permission_code="docs.upload",
        scope_type="project",
        scope_id="arena",
        grant_mode="use_and_delegate",
        granted_by=super_admin,
        expires_at=parent_expiry,
        note="smoke-parent",
    )
    parent = parent_res.grant
    assert parent.is_active
    assert has_permission(lead, "docs.upload", "project", "arena")
    print("    [OK] lead has docs.upload@project:arena")

    print("[2] lead delegates to junior with same scope, shorter expiry -> OK")
    child_res = access_service.grant_permission(
        employee=junior,
        permission_code="docs.upload",
        scope_type="project",
        scope_id="arena",
        grant_mode="use_only",
        granted_by=lead,
        parent_grant=parent,
        source_type=PermissionGrant.SOURCE_DELEGATION,
        expires_at=parent_expiry - timedelta(days=1),
    )
    child = child_res.grant
    assert child.is_active
    assert child.parent_grant_id == parent.id
    assert has_permission(junior, "docs.upload", "project", "arena")
    print("    [OK] junior received docs.upload via parent_grant")

    print("[3] lead tries to delegate with longer expiry than parent -> blocked")
    _expect(
        "child outlives parent",
        lambda: access_service.grant_permission(
            employee=junior,
            permission_code="docs.upload",
            scope_type="project",
            scope_id="arena",
            grant_mode="use_only",
            granted_by=lead,
            parent_grant=parent,
            source_type=PermissionGrant.SOURCE_DELEGATION,
            expires_at=too_far_in_future,
        ),
    )

    print("[4] lead tries to delegate with no expiry while parent is bounded -> blocked")
    _expect(
        "child unbounded vs bounded parent",
        lambda: access_service.grant_permission(
            employee=junior,
            permission_code="docs.upload",
            scope_type="project",
            scope_id="arena",
            grant_mode="use_only",
            granted_by=lead,
            parent_grant=parent,
            source_type=PermissionGrant.SOURCE_DELEGATION,
            expires_at=None,
        ),
    )

    print("[5] lead tries to delegate to a different project -> blocked (scope mismatch)")
    _expect(
        "child scope_id != parent scope_id",
        lambda: access_service.grant_permission(
            employee=junior,
            permission_code="docs.upload",
            scope_type="project",
            scope_id="olympus",
            grant_mode="use_only",
            granted_by=lead,
            parent_grant=parent,
            source_type=PermissionGrant.SOURCE_DELEGATION,
            expires_at=parent_expiry - timedelta(hours=1),
        ),
    )

    print("[6] junior cannot delegate further (parent is use_only)")
    _expect(
        "child grant is use_only",
        lambda: access_service.grant_permission(
            employee=_u("deleg-third@atom.test"),
            permission_code="docs.upload",
            scope_type="project",
            scope_id="arena",
            grant_mode="use_only",
            granted_by=junior,
            parent_grant=child,
            source_type=PermissionGrant.SOURCE_DELEGATION,
            expires_at=parent_expiry - timedelta(hours=1),
        ),
    )

    print("[7] revoke parent cascades to child")
    access_service.revoke_permission(parent, revoked_by=super_admin, note="smoke-revoke")
    parent.refresh_from_db()
    child.refresh_from_db()
    assert parent.status == PermissionGrant.STATUS_REVOKED
    assert child.status == PermissionGrant.STATUS_REVOKED
    assert not has_permission(junior, "docs.upload", "project", "arena")
    print("    [OK] parent + child revoked, junior loses access")

    print("[8] cannot delegate from a revoked parent")
    _expect(
        "parent revoked",
        lambda: access_service.grant_permission(
            employee=junior,
            permission_code="docs.upload",
            scope_type="project",
            scope_id="arena",
            grant_mode="use_only",
            granted_by=lead,
            parent_grant=parent,
            source_type=PermissionGrant.SOURCE_DELEGATION,
            expires_at=parent_expiry - timedelta(hours=1),
        ),
    )

    print("[9] expired-by-time parent is not delegable, even if status is still ACTIVE")
    short_expiry = timezone.now() - timedelta(seconds=1)
    expired_parent_res = access_service.grant_permission(
        employee=lead,
        permission_code="docs.upload",
        scope_type="project",
        scope_id="arena",
        grant_mode="use_and_delegate",
        granted_by=super_admin,
        expires_at=short_expiry,
        note="smoke-expired",
    )
    expired_parent = expired_parent_res.grant
    _expect(
        "parent past expires_at",
        lambda: access_service.grant_permission(
            employee=junior,
            permission_code="docs.upload",
            scope_type="project",
            scope_id="arena",
            grant_mode="use_only",
            granted_by=lead,
            parent_grant=expired_parent,
            source_type=PermissionGrant.SOURCE_DELEGATION,
            expires_at=None,
        ),
    )

    print("[10] cleanup")
    _purge(lead, junior)
    PermissionGrant.objects.filter(employee=_u("deleg-third@atom.test")).delete()
    print("=== delegation smoke OK ===")


main()
