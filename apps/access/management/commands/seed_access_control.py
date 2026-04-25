"""Idempotent seed for the access-control catalog.

Runs on clean DBs *and* on production — it only upserts and never removes
operator-managed flags. Safe to call during every deploy.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.access.seed import seed_all


class Command(BaseCommand):
    help = "Seed core PermissionDefinition / DelegationRule / RoleTemplate rows."

    def handle(self, *args, **options):  # type: ignore[override]
        result = seed_all()
        for section, (created, updated) in result.items():
            self.stdout.write(
                self.style.SUCCESS(f"{section}: +{created} new, {updated} updated")
            )
