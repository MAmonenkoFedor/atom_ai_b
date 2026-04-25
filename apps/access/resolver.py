"""Permission resolver — answers ``can this user do X in scope Y?``.

The resolver is deliberately dumb: it reads the current set of active grants
and role-template assignments for a user and combines them. It does *not*
write. All writes happen in :mod:`apps.access.service`.

Core rule (v1):

    A permission exists only when there is an active grant in a concrete
    scope, issued by an allowed source and not revoked / not expired.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from django.utils import timezone

from apps.access.models import (
    DelegationRule,
    PermissionDefinition,
    PermissionGrant,
    RoleTemplateAssignment,
    RoleTemplatePermission,
    SCOPE_BREADTH_ORDER,
    SCOPE_GLOBAL,
)


# ---------------------------------------------------------------------------
# Internal dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EffectivePermission:
    """One effective permission slot (after resolution)."""

    permission_code: str
    scope_type: str
    scope_id: str
    grant_mode: str  # ``use_only`` | ``use_and_delegate``
    source_type: str  # ``direct`` | ``role_template`` | ``delegation``
    source_label: str
    source_id: str
    expires_at: Optional[str]

    def as_dict(self) -> dict:
        return {
            "permission_code": self.permission_code,
            "scope_type": self.scope_type,
            "scope_id": self.scope_id or None,
            "grant_mode": self.grant_mode,
            "source_type": self.source_type,
            "source_label": self.source_label,
            "source_id": self.source_id or None,
            "expires_at": self.expires_at,
        }


# ---------------------------------------------------------------------------
# Scope matching helpers
# ---------------------------------------------------------------------------


def scope_covers(
    *,
    grant_scope_type: str,
    grant_scope_id: str,
    required_scope_type: str,
    required_scope_id: str,
) -> bool:
    """Return True if a grant's scope covers the requested scope.

    Rules:

    * A ``global`` grant covers every request.
    * A ``company`` / ``department`` / ``project`` grant only covers the exact
      same scope type *and* same id.
    * ``self`` covers only ``self`` with matching id.
    """

    if grant_scope_type == SCOPE_GLOBAL:
        return True
    if grant_scope_type != required_scope_type:
        return False
    # Empty scope_id in a grant ≠ "any" — it means "unscoped"; only matches
    # a request with an equally empty id.
    return (grant_scope_id or "") == (required_scope_id or "")


def _is_narrower_or_equal(candidate_type: str, parent_type: str) -> bool:
    candidate = SCOPE_BREADTH_ORDER.get(candidate_type, 99)
    parent = SCOPE_BREADTH_ORDER.get(parent_type, 99)
    return candidate >= parent


# ---------------------------------------------------------------------------
# Loading active grants
# ---------------------------------------------------------------------------


def _now():
    return timezone.now()


def _fresh_grants_qs(user):
    """Grants that are still ``active`` and not expired. Mutates status of any
    stale grants on the fly so the caller sees consistent data.
    """

    now = _now()

    # Bump any expired rows lazily. This is cheap and keeps the resolver
    # deterministic without requiring a cron job.
    stale = PermissionGrant.objects.filter(
        employee=user,
        status=PermissionGrant.STATUS_ACTIVE,
        expires_at__isnull=False,
        expires_at__lt=now,
    )
    if stale.exists():
        stale.update(status=PermissionGrant.STATUS_EXPIRED)

    return PermissionGrant.objects.filter(
        employee=user, status=PermissionGrant.STATUS_ACTIVE
    )


def _template_grants_for(user) -> list[EffectivePermission]:
    assignments = (
        RoleTemplateAssignment.objects.filter(employee=user, is_active=True)
        .select_related("role_template")
    )
    if not assignments:
        return []

    template_ids = [a.role_template_id for a in assignments]
    template_permissions = RoleTemplatePermission.objects.filter(
        role_template_id__in=template_ids, default_enabled=True
    )
    permissions_by_template: dict[int, list[RoleTemplatePermission]] = {}
    for perm in template_permissions:
        permissions_by_template.setdefault(perm.role_template_id, []).append(perm)

    result: list[EffectivePermission] = []
    for a in assignments:
        template = a.role_template
        if not template.is_active:
            continue
        for perm in permissions_by_template.get(template.id, ()):  # type: ignore[union-attr]
            result.append(
                EffectivePermission(
                    permission_code=perm.permission_code,
                    scope_type=a.scope_type,
                    scope_id=a.scope_id,
                    grant_mode=perm.grant_mode,
                    source_type="role_template",
                    source_label=template.name or template.code,
                    source_id=str(template.id),
                    expires_at=None,
                )
            )
    return result


def _direct_grants_for(user) -> list[EffectivePermission]:
    grants = list(_fresh_grants_qs(user))
    return [
        EffectivePermission(
            permission_code=g.permission_code,
            scope_type=g.scope_type,
            scope_id=g.scope_id,
            grant_mode=g.grant_mode,
            source_type=(
                "delegation" if g.source_type == PermissionGrant.SOURCE_DELEGATION else "direct"
            ),
            source_label=_label_for_grant(g),
            source_id=str(g.id),
            expires_at=g.expires_at.isoformat() if g.expires_at else None,
        )
        for g in grants
    ]


def _label_for_grant(grant: PermissionGrant) -> str:
    if grant.source_type == PermissionGrant.SOURCE_DELEGATION:
        return "Делегирование"
    if grant.source_type == PermissionGrant.SOURCE_ROLE_TEMPLATE:
        return "Шаблон"
    if grant.source_type == PermissionGrant.SOURCE_SYSTEM_SEED:
        return "Системный seed"
    return "Прямое назначение"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_effective_permissions(user) -> list[dict]:
    """Every permission the user currently has, with the *strongest* grant_mode
    per (code, scope).
    """

    if user is None or not user.is_authenticated:
        return []

    all_rows = _template_grants_for(user) + _direct_grants_for(user)
    # Coalesce: use_and_delegate beats use_only for the same (code, scope).
    best: dict[tuple[str, str, str], EffectivePermission] = {}
    for row in all_rows:
        key = (row.permission_code, row.scope_type, row.scope_id or "")
        existing = best.get(key)
        if existing is None or _mode_stronger(row.grant_mode, existing.grant_mode):
            best[key] = row
    return [row.as_dict() for row in best.values()]


def list_permission_sources(user) -> list[dict]:
    """Same as :func:`list_effective_permissions` but keeps every source of
    every permission so the UI can render "where this came from" tables.
    """

    if user is None or not user.is_authenticated:
        return []

    rows = _template_grants_for(user) + _direct_grants_for(user)
    return [row.as_dict() for row in rows]


def has_permission(
    user,
    permission_code: str,
    scope_type: str = SCOPE_GLOBAL,
    scope_id: str = "",
) -> bool:
    """True iff ``user`` currently has ``permission_code`` covering the scope."""

    if user is None or not user.is_authenticated:
        return False

    definition = PermissionDefinition.objects.filter(
        code=permission_code, is_active=True
    ).first()
    if definition is None:
        return False

    for row in _template_grants_for(user):
        if row.permission_code != permission_code:
            continue
        if scope_covers(
            grant_scope_type=row.scope_type,
            grant_scope_id=row.scope_id,
            required_scope_type=scope_type,
            required_scope_id=scope_id,
        ):
            return True

    active_grants = _fresh_grants_qs(user).filter(permission_code=permission_code)
    for g in active_grants:
        if scope_covers(
            grant_scope_type=g.scope_type,
            grant_scope_id=g.scope_id,
            required_scope_type=scope_type,
            required_scope_id=scope_id,
        ):
            return True
    return False


def can_delegate(
    user,
    permission_code: str,
    target_scope_type: str,
    target_scope_id: str = "",
) -> bool:
    """True iff ``user`` holds a ``use_and_delegate`` grant that authorises
    issuing a new grant in the target scope.

    Checks, in order:

    1. Permission definition exists and ``can_be_delegated`` is True.
    2. User has at least one active grant (direct or via template) with
       ``grant_mode=use_and_delegate`` whose scope is broader-or-equal to the
       target scope.
    3. The :class:`DelegationRule` for (from_scope, to_scope) explicitly
       allows delegation.
    """

    if user is None or not user.is_authenticated:
        return False

    definition = PermissionDefinition.objects.filter(
        code=permission_code, is_active=True, can_be_delegated=True
    ).first()
    if definition is None:
        return False

    eligible_sources: list[tuple[str, str]] = []

    # Gather candidates from templates
    for row in _template_grants_for(user):
        if row.permission_code != permission_code:
            continue
        if row.grant_mode != PermissionGrant.GRANT_MODE_USE_AND_DELEGATE:
            continue
        if not _is_narrower_or_equal(target_scope_type, row.scope_type):
            continue
        if (
            row.scope_type != SCOPE_GLOBAL
            and row.scope_type == target_scope_type
            and (row.scope_id or "") != (target_scope_id or "")
        ):
            continue
        eligible_sources.append((row.scope_type, row.scope_id or ""))

    # Gather candidates from direct grants
    direct_qs = _fresh_grants_qs(user).filter(
        permission_code=permission_code,
        grant_mode=PermissionGrant.GRANT_MODE_USE_AND_DELEGATE,
    )
    for g in direct_qs:
        if not _is_narrower_or_equal(target_scope_type, g.scope_type):
            continue
        if (
            g.scope_type != SCOPE_GLOBAL
            and g.scope_type == target_scope_type
            and (g.scope_id or "") != (target_scope_id or "")
        ):
            continue
        eligible_sources.append((g.scope_type, g.scope_id or ""))

    if not eligible_sources:
        return False

    # Check delegation rule for each candidate (scope transition)
    for from_scope, _from_id in eligible_sources:
        rule = DelegationRule.objects.filter(
            permission_code=permission_code,
            from_scope_type=from_scope,
            to_scope_type=target_scope_type,
        ).first()
        if rule is None:
            # Default when no rule exists: require same-scope only.
            if from_scope == target_scope_type:
                return True
            continue
        if not rule.allow_delegate:
            continue
        if rule.allow_same_scope_only and from_scope != target_scope_type:
            continue
        if (
            not rule.allow_narrower_scope
            and SCOPE_BREADTH_ORDER.get(target_scope_type, 0)
            > SCOPE_BREADTH_ORDER.get(from_scope, 0)
        ):
            continue
        return True
    return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_MODE_STRENGTH = {
    PermissionGrant.GRANT_MODE_USE_ONLY: 1,
    PermissionGrant.GRANT_MODE_USE_AND_DELEGATE: 2,
}


def _mode_stronger(candidate: str, current: str) -> bool:
    return _MODE_STRENGTH.get(candidate, 0) > _MODE_STRENGTH.get(current, 0)


__all__: Sequence[str] = (
    "EffectivePermission",
    "has_permission",
    "can_delegate",
    "list_effective_permissions",
    "list_permission_sources",
    "scope_covers",
)
