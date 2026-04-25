"""Smoke for ``permission.delegation_blocked`` audit events.

Every rejection branch in :func:`apps.access.service._assert_delegation_allowed`
(plus the early ``permission_not_delegable`` and ``missing_parent_grant``
guards in :func:`grant_permission`) must surface as a structured row in
:class:`apps.audit.models.AuditEvent` with:

* ``event_type = "permission.delegation_blocked"``
* ``action     = "delegate_blocked"``
* ``payload.reason`` == one of :data:`apps.access.service.DELEGATION_BLOCK_REASONS`
* actor / target / permission code / scope captured for forensics

We trigger every reason once and confirm exactly one new audit row for it.

Run::

    .\\.venv\\Scripts\\python.exe manage.py shell -c "exec(open('scripts/access_delegation_audit_smoke.py', encoding='utf8').read())"
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.access import service as access_service
from apps.access.models import PermissionGrant
from apps.audit.models import AuditEvent

User = get_user_model()
EVENT_TYPE = "permission.delegation_blocked"


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


def _last_block_event() -> AuditEvent | None:
    return (
        AuditEvent.objects.filter(event_type=EVENT_TYPE)
        .order_by("-created_at", "-id")
        .first()
    )


def _expect_block(label: str, expected_reason: str, fn) -> AuditEvent:
    before = AuditEvent.objects.filter(event_type=EVENT_TYPE).count()
    try:
        fn()
    except access_service.DelegationNotAllowed as exc:
        actual_reason = getattr(exc, "reason", "")
        if actual_reason != expected_reason:
            print(
                f"    [FAIL] {label}: exception reason '{actual_reason}'"
                f" != expected '{expected_reason}'"
            )
            raise SystemExit(1)
    else:
        print(f"    [FAIL] {label}: should have been rejected")
        raise SystemExit(1)

    after = AuditEvent.objects.filter(event_type=EVENT_TYPE).count()
    if after != before + 1:
        print(
            f"    [FAIL] {label}: expected exactly 1 new audit row, "
            f"got {after - before}"
        )
        raise SystemExit(1)

    event = _last_block_event()
    assert event is not None
    if event.action != "delegate_blocked":
        print(f"    [FAIL] {label}: action='{event.action}', expected 'delegate_blocked'")
        raise SystemExit(1)
    payload = event.payload or {}
    if payload.get("reason") != expected_reason:
        print(
            f"    [FAIL] {label}: payload.reason='{payload.get('reason')}'"
            f" != expected '{expected_reason}'"
        )
        raise SystemExit(1)

    print(f"    [OK] {label}: reason={expected_reason} audit_id={event.id}")
    return event


def main() -> None:
    print("=== delegation audit smoke ===")

    super_admin = _u("audit-deleg-super@atom.test", is_super=True)
    lead = _u("audit-deleg-lead@atom.test")
    other_lead = _u("audit-deleg-other@atom.test")
    junior = _u("audit-deleg-junior@atom.test")
    third = _u("audit-deleg-third@atom.test")
    _purge(lead, other_lead, junior, third)

    parent_expiry = timezone.now() + timedelta(days=7)

    print("[1] permission_not_delegable: project.create has can_be_delegated=False")
    _expect_block(
        "permission_not_delegable",
        "permission_not_delegable",
        lambda: access_service.grant_permission(
            employee=junior,
            permission_code="project.create",
            scope_type="company",
            scope_id="atom",
            grant_mode="use_and_delegate",
            granted_by=super_admin,
            note="audit-perm-not-delegable",
        ),
    )

    print("[2] missing_parent_grant: source=delegation but parent_grant=None")
    _expect_block(
        "missing_parent_grant",
        "missing_parent_grant",
        lambda: access_service.grant_permission(
            employee=junior,
            permission_code="docs.upload",
            scope_type="project",
            scope_id="arena",
            grant_mode="use_only",
            granted_by=lead,
            parent_grant=None,
            source_type=PermissionGrant.SOURCE_DELEGATION,
            expires_at=parent_expiry,
            note="audit-missing-parent",
        ),
    )

    # Set up a real delegable parent for downstream branches.
    parent = access_service.grant_permission(
        employee=lead,
        permission_code="docs.upload",
        scope_type="project",
        scope_id="arena",
        grant_mode="use_and_delegate",
        granted_by=super_admin,
        expires_at=parent_expiry,
        note="audit-parent",
    ).grant

    print("[3] parent_not_owned: other_lead tries to delegate from lead's parent")
    _expect_block(
        "parent_not_owned",
        "parent_not_owned",
        lambda: access_service.grant_permission(
            employee=junior,
            permission_code="docs.upload",
            scope_type="project",
            scope_id="arena",
            grant_mode="use_only",
            granted_by=other_lead,
            parent_grant=parent,
            source_type=PermissionGrant.SOURCE_DELEGATION,
            expires_at=parent_expiry - timedelta(hours=1),
        ),
    )

    print("[4] permission_mismatch: parent covers docs.upload, child asks docs.view")
    _expect_block(
        "permission_mismatch",
        "permission_mismatch",
        lambda: access_service.grant_permission(
            employee=junior,
            permission_code="docs.view",
            scope_type="project",
            scope_id="arena",
            grant_mode="use_only",
            granted_by=lead,
            parent_grant=parent,
            source_type=PermissionGrant.SOURCE_DELEGATION,
            expires_at=parent_expiry - timedelta(hours=1),
        ),
    )

    print("[5] child_unbounded_vs_bounded: parent has expiry, child has none")
    _expect_block(
        "child_unbounded_vs_bounded",
        "child_unbounded_vs_bounded",
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

    print("[6] child_outlives_parent: child.expires_at > parent.expires_at")
    _expect_block(
        "child_outlives_parent",
        "child_outlives_parent",
        lambda: access_service.grant_permission(
            employee=junior,
            permission_code="docs.upload",
            scope_type="project",
            scope_id="arena",
            grant_mode="use_only",
            granted_by=lead,
            parent_grant=parent,
            source_type=PermissionGrant.SOURCE_DELEGATION,
            expires_at=parent_expiry + timedelta(days=14),
        ),
    )

    print("[7] scope_id_mismatch: same scope_type, different scope_id")
    _expect_block(
        "scope_id_mismatch",
        "scope_id_mismatch",
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

    print("[8] parent_use_only: child of a use_only grant cannot delegate further")
    use_only_child = access_service.grant_permission(
        employee=junior,
        permission_code="docs.upload",
        scope_type="project",
        scope_id="arena",
        grant_mode="use_only",
        granted_by=lead,
        parent_grant=parent,
        source_type=PermissionGrant.SOURCE_DELEGATION,
        expires_at=parent_expiry - timedelta(hours=2),
    ).grant
    _expect_block(
        "parent_use_only",
        "parent_use_only",
        lambda: access_service.grant_permission(
            employee=third,
            permission_code="docs.upload",
            scope_type="project",
            scope_id="arena",
            grant_mode="use_only",
            granted_by=junior,
            parent_grant=use_only_child,
            source_type=PermissionGrant.SOURCE_DELEGATION,
            expires_at=parent_expiry - timedelta(hours=3),
        ),
    )

    print("[9] parent_inactive: revoke parent, then try to delegate from it")
    access_service.revoke_permission(parent, revoked_by=super_admin, note="audit-revoke")
    parent.refresh_from_db()
    _expect_block(
        "parent_inactive",
        "parent_inactive",
        lambda: access_service.grant_permission(
            employee=junior,
            permission_code="docs.upload",
            scope_type="project",
            scope_id="arena",
            grant_mode="use_only",
            granted_by=lead,
            parent_grant=parent,
            source_type=PermissionGrant.SOURCE_DELEGATION,
            expires_at=parent_expiry - timedelta(hours=4),
        ),
    )

    print("[10] parent_expired: parent active in DB but past expires_at")
    expired_parent = access_service.grant_permission(
        employee=lead,
        permission_code="docs.upload",
        scope_type="project",
        scope_id="arena",
        grant_mode="use_and_delegate",
        granted_by=super_admin,
        expires_at=timezone.now() - timedelta(seconds=2),
        note="audit-expired-parent",
    ).grant
    _expect_block(
        "parent_expired",
        "parent_expired",
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

    print("[11] payload sanity: actor_id, target_employee_id, scope captured")
    sample = (
        AuditEvent.objects.filter(event_type=EVENT_TYPE)
        .order_by("-created_at", "-id")
        .first()
    )
    assert sample is not None
    payload = sample.payload or {}
    for key in ("permission_code", "reason", "scope_type", "actor_id", "target_employee_id"):
        if key not in payload:
            print(f"    [FAIL] payload missing required key: {key}")
            raise SystemExit(1)
    print(
        "    [OK] payload keys present:",
        sorted(k for k in payload.keys()),
    )

    print("[12] cleanup")
    _purge(lead, other_lead, junior, third)
    AuditEvent.objects.filter(
        event_type=EVENT_TYPE, payload__note__startswith="audit-"
    ).delete()
    print("=== delegation audit smoke OK ===")


main()
