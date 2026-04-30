"""Validate DB-level access-control privacy defaults."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.access.checks import check_ai_workspace_privacy_invariants


class Command(BaseCommand):
    help = "Check AI workspace privacy defaults in access-control catalog."

    def handle(self, *args, **options):  # type: ignore[override]
        result = check_ai_workspace_privacy_invariants()
        if result.ok:
            self.stdout.write(self.style.SUCCESS("access privacy defaults: OK"))
            return

        for line in result.errors:
            self.stderr.write(self.style.ERROR(line))
        raise CommandError("access privacy defaults check failed")
