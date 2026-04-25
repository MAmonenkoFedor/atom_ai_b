"""Verify expire_access_grants management command on a synthetic grant."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from apps.access.models import PermissionGrant


User = get_user_model()


def main() -> None:
    actor = User.objects.filter(username="super_admin_test").first()
    target = User.objects.filter(username="employee_test").first()
    assert actor and target, "seed_test_credentials first"

    PermissionGrant.objects.filter(employee=target, note__startswith="expire-smoke").delete()

    past = timezone.now() - timedelta(hours=1)
    g = PermissionGrant.objects.create(
        employee=target,
        permission_code="docs.upload",
        scope_type="project",
        scope_id="arena",
        grant_mode=PermissionGrant.GRANT_MODE_USE_ONLY,
        granted_by=actor,
        expires_at=past,
        status=PermissionGrant.STATUS_ACTIVE,
        note="expire-smoke",
    )
    print(f"created grant id={g.id} expires_at={g.expires_at} status={g.status}")

    print("--- dry-run ---")
    call_command("expire_access_grants", "--dry-run")

    print("--- real run ---")
    call_command("expire_access_grants")

    g.refresh_from_db()
    print(f"after: id={g.id} status={g.status}")
    assert g.status == PermissionGrant.STATUS_EXPIRED, g.status

    PermissionGrant.objects.filter(employee=target, note="expire-smoke").delete()
    print("cleanup OK")


main()
