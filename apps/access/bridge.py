"""Bridge between :mod:`apps.access` grants and legacy ``UserCapability`` codes.

The legacy capability system (:mod:`apps.identity.capabilities`) is used by a
lot of existing views via ``HasCapability``. The new access service is the
single source of truth for permissions, but we cannot rewrite every view in
one go. Instead we expose :func:`capabilities_from_access` which maps the
active, non-revoked grants of a user to legacy capability codes. The result
is meant to be unioned with role-bundle capabilities and explicit
``UserCapability`` rows (see ``apps.core.api.permissions.effective_capabilities``).

Mapping rules (v1):

* a grant only contributes to global/company-wide capabilities if its
  ``scope_type`` is ``global`` or ``company`` (capabilities are not scoped),
* mappings cover the platform-wide management codes; scope-specific access
  codes (``project.*``, ``department.*``, ``docs.*`` …) are intentionally not
  mapped — they should be checked through :class:`HasAccessPermission`
  instead.
"""

from __future__ import annotations

from typing import Iterable

from django.utils import timezone

from apps.access.models import (
    PermissionGrant,
    SCOPE_COMPANY,
    SCOPE_GLOBAL,
)
from apps.identity import capabilities as caps


# Access permission code -> legacy capability codes that it implies.
# Only includes platform-wide management codes (super-admin / company-admin
# territory). Project / department / document / task codes are deliberately
# omitted because the legacy capability layer doesn't model their scope.
_ACCESS_TO_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "rights.grant": (caps.CAPABILITIES_MANAGE,),
    "rights.revoke": (caps.CAPABILITIES_MANAGE,),
    "roles.assign": (caps.ROLES_MANAGE,),
    "ai.models.manage": (
        caps.LLM_PROVIDERS_MANAGE,
        caps.LLM_MODELS_MANAGE,
    ),
}


_GLOBAL_OR_COMPANY = (SCOPE_GLOBAL, SCOPE_COMPANY)


def capabilities_from_access(user) -> set[str]:
    """Return legacy capability codes implied by active access grants.

    Returns an empty set for anonymous / inactive users or when no active
    grant maps to a known capability.
    """

    if not user or not getattr(user, "is_authenticated", False):
        return set()

    codes = list(_ACCESS_TO_CAPABILITIES.keys())
    if not codes:
        return set()

    now = timezone.now()
    grants: Iterable[PermissionGrant] = PermissionGrant.objects.filter(
        employee=user,
        permission_code__in=codes,
        scope_type__in=_GLOBAL_OR_COMPANY,
        status=PermissionGrant.STATUS_ACTIVE,
        revoked_at__isnull=True,
    ).only("permission_code", "expires_at")

    result: set[str] = set()
    for grant in grants:
        if grant.expires_at is not None and grant.expires_at <= now:
            continue
        for cap in _ACCESS_TO_CAPABILITIES.get(grant.permission_code, ()):
            result.add(cap)
    return result
