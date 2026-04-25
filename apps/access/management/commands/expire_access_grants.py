"""Mark expired access grants as ``STATUS_EXPIRED``.

The resolver already filters out grants whose ``expires_at`` is in the past,
so users do not see stale permissions. This command is hygiene — it flips
the database status from ``active`` to ``expired`` and writes one
``PermissionAuditLog`` entry per affected grant so the history stays clean.

Run periodically (cron / scheduler / Celery beat). Idempotent.

Usage::

    .\\.venv\\Scripts\\python.exe manage.py expire_access_grants
    .\\.venv\\Scripts\\python.exe manage.py expire_access_grants --dry-run
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.access import service as access_service
from apps.access.models import PermissionAuditLog, PermissionGrant


class Command(BaseCommand):
    help = "Flip status to 'expired' for every active grant whose expires_at has passed."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report what would change without writing.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Optional cap on the number of grants processed in one run.",
        )

    def handle(self, *args, **options):
        dry: bool = options["dry_run"]
        limit: int = options["limit"] or 0

        now = timezone.now()
        qs = PermissionGrant.objects.filter(
            status=PermissionGrant.STATUS_ACTIVE,
            expires_at__isnull=False,
            expires_at__lte=now,
        ).select_related("employee", "granted_by").order_by("expires_at")
        if limit > 0:
            qs = qs[:limit]

        total = qs.count()
        if total == 0:
            self.stdout.write("expire_access_grants: nothing to do.")
            return

        if dry:
            self.stdout.write(f"expire_access_grants [dry-run]: {total} grant(s) would expire.")
            for grant in qs[:25]:
                self.stdout.write(
                    f"  - id={grant.id} {grant.permission_code} "
                    f"@ {grant.scope_type}:{grant.scope_id or '-'} "
                    f"emp={getattr(grant.employee, 'email', grant.employee_id)} "
                    f"expires_at={grant.expires_at.isoformat()}"
                )
            return

        affected = 0
        for grant in list(qs):
            with transaction.atomic():
                old = {
                    "status": grant.status,
                    "expires_at": grant.expires_at.isoformat() if grant.expires_at else None,
                }
                grant.status = PermissionGrant.STATUS_EXPIRED
                grant.save(update_fields=["status"])
                access_service._record_audit(  # noqa: SLF001 — internal helper, same package
                    request=None,
                    actor=None,
                    target=grant.employee,
                    action=PermissionAuditLog.ACTION_GRANT_EXPIRED,
                    permission_code=grant.permission_code,
                    scope_type=grant.scope_type,
                    scope_id=grant.scope_id,
                    old_value=old,
                    new_value={"status": grant.status},
                    note="auto-expired by expire_access_grants",
                )
                affected += 1

        self.stdout.write(f"expire_access_grants: marked {affected}/{total} grants as expired.")
