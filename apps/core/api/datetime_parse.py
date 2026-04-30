from __future__ import annotations

from datetime import datetime, time

from django.utils import dateparse, timezone
from rest_framework.exceptions import ValidationError


def parse_datetime_param(raw: str, param_name: str, *, is_end: bool):
    dt = dateparse.parse_datetime(raw)
    if dt is not None:
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt

    d = dateparse.parse_date(raw)
    if d is not None:
        boundary_time = time.max if is_end else time.min
        dt = datetime.combine(d, boundary_time)
        return timezone.make_aware(dt, timezone.get_current_timezone())

    raise ValidationError(
        {
            "detail": (
                f"Invalid {param_name}. Use ISO datetime "
                f"(e.g. 2026-04-14T10:00:00+03:00) or date (YYYY-MM-DD)."
            )
        }
    )
