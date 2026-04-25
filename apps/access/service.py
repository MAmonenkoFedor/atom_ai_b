"""Write-side of the access-control service.

All code paths that mutate permissions (grant, revoke, delegate, assign /
remove template) go through here. The service:

* validates the inputs against :class:`PermissionDefinition` and
  :class:`DelegationRule`;
* creates the row;
* emits both a structured :class:`PermissionAuditLog` row *and* a generic
  :func:`apps.audit.service.emit_audit_event` record.

All entry points take an optional ``request`` so the audit trail captures
IP / trace id. Callers that don't have a request (scripts, seeds) can omit
it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.access import resolver
from apps.access.models import (
    DelegationRule,
    PermissionAuditLog,
    PermissionDefinition,
    PermissionGrant,
    RoleTemplate,
    RoleTemplateAssignment,
    RoleTemplatePermission,
    SCOPE_BREADTH_ORDER,
    SCOPE_GLOBAL,
)

try:
    from apps.audit.service import emit_audit_event  # type: ignore
except Exception:  # pragma: no cover — tolerate standalone imports

    def emit_audit_event(*_args, **_kwargs):
        return None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AccessControlError(Exception):
    """Base error for any validation failure inside the service."""


class UnknownPermission(AccessControlError):
    pass


class ScopeNotAllowed(AccessControlError):
    pass


class DelegationNotAllowed(AccessControlError):
    """Raised when a delegation attempt violates the access policy.

    The ``reason`` attribute carries a stable machine-readable code that we
    surface in audit events (``permission.delegation_blocked``) and tests.
    Keep new codes lowercase ``snake_case`` and add them to
    :data:`DELEGATION_BLOCK_REASONS`.
    """

    def __init__(self, message: str, *, reason: str = "unspecified"):
        super().__init__(message)
        self.reason = reason or "unspecified"


DELEGATION_BLOCK_REASONS: tuple[str, ...] = (
    "permission_not_delegable",
    "parent_not_owned",
    "parent_inactive",
    "parent_expired",
    "parent_use_only",
    "mode_escalation",
    "permission_mismatch",
    "child_unbounded_vs_bounded",
    "child_outlives_parent",
    "scope_broader",
    "scope_id_mismatch",
    "no_delegation_rule",
    "rule_disabled",
    "rule_same_scope_only",
    "max_depth_exceeded",
    "missing_parent_grant",
    "missing_actor",
    "unspecified",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request_id(request) -> str:
    if request is None:
        return ""
    trace = (
        request.headers.get("X-Trace-Id") if hasattr(request, "headers") else None
    )
    if trace:
        return trace[:64]
    meta = getattr(request, "META", {}) or {}
    return (meta.get("HTTP_X_TRACE_ID") or meta.get("HTTP_X_REQUEST_ID") or "")[:64]


def _definition_or_fail(code: str) -> PermissionDefinition:
    try:
        definition = PermissionDefinition.objects.get(code=code)
    except PermissionDefinition.DoesNotExist as exc:
        raise UnknownPermission(f"Unknown permission: {code}") from exc
    if not definition.is_active:
        raise UnknownPermission(f"Permission disabled: {code}")
    return definition


def _assert_scope_allowed(definition: PermissionDefinition, scope_type: str) -> None:
    allowed = list(definition.allowed_scopes or [])
    if allowed and scope_type not in allowed:
        raise ScopeNotAllowed(
            f"Permission {definition.code} cannot be granted with scope "
            f"{scope_type}; allowed: {', '.join(allowed)}"
        )


def _emit_delegation_blocked(
    *,
    request,
    actor,
    target,
    permission_code: str,
    target_scope_type: str,
    target_scope_id: str,
    target_grant_mode: str,
    target_expires_at,
    parent_grant: Optional[PermissionGrant],
    reason: str,
    message: str,
    note: str = "",
) -> None:
    """Emit a structured ``permission.delegation_blocked`` audit event.

    Writes a row into :class:`apps.audit.models.AuditEvent` so security review
    sees not only successful grants but also rejected delegation attempts —
    actor, target, permission, scope, parent grant and the rejection
    ``reason`` (one of :data:`DELEGATION_BLOCK_REASONS`).

    Designed to be safe in any caller context: works with a real DRF request
    (captures path/method/ip/trace_id) and without one (scripts, seeds) — in
    that case it writes the row directly via the ORM.
    """

    payload = {
        "permission_code": permission_code,
        "scope_type": target_scope_type or "",
        "scope_id": target_scope_id or "",
        "grant_mode": target_grant_mode or "",
        "target_expires_at": target_expires_at.isoformat() if target_expires_at else None,
        "parent_grant_id": getattr(parent_grant, "id", None),
        "parent_permission_code": getattr(parent_grant, "permission_code", None),
        "parent_scope_type": getattr(parent_grant, "scope_type", None),
        "parent_scope_id": getattr(parent_grant, "scope_id", None),
        "parent_expires_at": (
            parent_grant.expires_at.isoformat()
            if (parent_grant and parent_grant.expires_at)
            else None
        ),
        "actor_id": getattr(actor, "id", None),
        "actor_username": getattr(actor, "username", None),
        "target_employee_id": getattr(target, "id", None),
        "target_username": getattr(target, "username", None),
        "reason": reason or "unspecified",
        "message": message,
        "note": note or "",
    }

    if request is not None:
        try:
            emit_audit_event(
                request,
                event_type="permission.delegation_blocked",
                entity_type="permission_grant",
                entity_id="",
                action="delegate_blocked",
                payload=payload,
            )
            return
        except Exception:  # pragma: no cover — fall through to direct write
            pass

    try:
        from apps.audit.models import AuditEvent  # local to dodge import cycles
    except Exception:  # pragma: no cover — audit app unavailable
        return

    company_id = ""
    if actor is not None and getattr(actor, "is_authenticated", False):
        company_id = str(getattr(actor, "organization_id", "") or "")
    AuditEvent.objects.create(
        actor=actor if (actor and getattr(actor, "is_authenticated", False)) else None,
        actor_role="",
        company_id=company_id,
        department_id="",
        event_type="permission.delegation_blocked",
        entity_type="permission_grant",
        entity_id="",
        action="delegate_blocked",
        project_id=str(target_scope_id) if (target_scope_type or "") == "project" else "",
        task_id="",
        chat_id="",
        request_path="",
        request_method="",
        ip_address=None,
        user_agent="",
        trace_id="",
        payload=payload,
    )


def _record_audit(
    *,
    request,
    actor,
    target,
    action: str,
    permission_code: str = "",
    scope_type: str = "",
    scope_id: str = "",
    old_value: Optional[dict] = None,
    new_value: Optional[dict] = None,
    note: str = "",
) -> PermissionAuditLog:
    """Persist an entry in :class:`PermissionAuditLog` and also emit a generic
    :class:`apps.audit.models.AuditEvent` so the existing audit UI surfaces the
    change automatically.
    """

    entry = PermissionAuditLog.objects.create(
        actor=actor if (actor and actor.is_authenticated) else None,
        target_employee=target,
        action=action,
        permission_code=permission_code or "",
        scope_type=scope_type or "",
        scope_id=scope_id or "",
        old_value=old_value or {},
        new_value=new_value or {},
        note=note or "",
        request_id=_request_id(request),
    )

    if request is not None:
        try:
            emit_audit_event(
                request,
                event_type="access_control",
                entity_type="permission_grant",
                entity_id=str(entry.id),
                action=action,
                payload={
                    "target_employee_id": getattr(target, "id", None),
                    "permission_code": permission_code,
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "old_value": entry.old_value,
                    "new_value": entry.new_value,
                    "note": note,
                },
            )
        except Exception:  # pragma: no cover — never break the main write
            pass

    return entry


# ---------------------------------------------------------------------------
# Grants
# ---------------------------------------------------------------------------


@dataclass
class GrantPermissionResult:
    grant: PermissionGrant
    audit: PermissionAuditLog


def grant_permission(
    *,
    employee,
    permission_code: str,
    scope_type: str = SCOPE_GLOBAL,
    scope_id: str = "",
    grant_mode: str = PermissionGrant.GRANT_MODE_USE_ONLY,
    granted_by=None,
    expires_at=None,
    note: str = "",
    source_type: str = PermissionGrant.SOURCE_MANUAL,
    source_id: str = "",
    parent_grant: Optional[PermissionGrant] = None,
    request=None,
) -> GrantPermissionResult:
    """Create a new active :class:`PermissionGrant`.

    ``granted_by`` may be ``None`` only for ``source_type`` in
    (``system_seed``, ``role_template``). For ``manual`` / ``delegation`` we
    demand a non-null actor — the audit log needs it.

    Validation runs *outside* the write transaction so that
    :func:`_emit_delegation_blocked` can persist a
    ``permission.delegation_blocked`` audit row before re-raising — otherwise
    the row would be rolled back together with the failed grant.
    """

    definition = _definition_or_fail(permission_code)
    _assert_scope_allowed(definition, scope_type)

    if grant_mode not in (
        PermissionGrant.GRANT_MODE_USE_ONLY,
        PermissionGrant.GRANT_MODE_USE_AND_DELEGATE,
    ):
        raise ValidationError(f"Unknown grant_mode: {grant_mode}")

    if grant_mode == PermissionGrant.GRANT_MODE_USE_AND_DELEGATE and not definition.can_be_delegated:
        exc = DelegationNotAllowed(
            f"Permission {permission_code} cannot be granted in use_and_delegate mode.",
            reason="permission_not_delegable",
        )
        _emit_delegation_blocked(
            request=request,
            actor=granted_by,
            target=employee,
            permission_code=permission_code,
            target_scope_type=scope_type,
            target_scope_id=scope_id,
            target_grant_mode=grant_mode,
            target_expires_at=expires_at,
            parent_grant=parent_grant,
            reason=exc.reason,
            message=str(exc),
            note=note,
        )
        raise exc

    if source_type == PermissionGrant.SOURCE_DELEGATION:
        if granted_by is None:
            raise AccessControlError("Delegation requires a non-null granted_by")
        if parent_grant is None:
            exc = DelegationNotAllowed(
                "Delegation requires a parent_grant",
                reason="missing_parent_grant",
            )
            _emit_delegation_blocked(
                request=request,
                actor=granted_by,
                target=employee,
                permission_code=permission_code,
                target_scope_type=scope_type,
                target_scope_id=scope_id,
                target_grant_mode=grant_mode,
                target_expires_at=expires_at,
                parent_grant=None,
                reason=exc.reason,
                message=str(exc),
                note=note,
            )
            raise exc
        try:
            _assert_delegation_allowed(
                delegator=granted_by,
                permission_code=permission_code,
                parent_grant=parent_grant,
                target_scope_type=scope_type,
                target_scope_id=scope_id,
                target_expires_at=expires_at,
                target_grant_mode=grant_mode,
            )
        except DelegationNotAllowed as exc:
            _emit_delegation_blocked(
                request=request,
                actor=granted_by,
                target=employee,
                permission_code=permission_code,
                target_scope_type=scope_type,
                target_scope_id=scope_id,
                target_grant_mode=grant_mode,
                target_expires_at=expires_at,
                parent_grant=parent_grant,
                reason=getattr(exc, "reason", "") or "unspecified",
                message=str(exc),
                note=note,
            )
            raise

    if source_type == PermissionGrant.SOURCE_MANUAL and granted_by is None:
        raise AccessControlError("Manual grants require a non-null granted_by")

    return _grant_permission_atomic(
        employee=employee,
        permission_code=permission_code,
        scope_type=scope_type,
        scope_id=scope_id,
        grant_mode=grant_mode,
        granted_by=granted_by,
        expires_at=expires_at,
        note=note,
        source_type=source_type,
        source_id=source_id,
        parent_grant=parent_grant,
        request=request,
    )


@transaction.atomic
def _grant_permission_atomic(
    *,
    employee,
    permission_code: str,
    scope_type: str,
    scope_id: str,
    grant_mode: str,
    granted_by,
    expires_at,
    note: str,
    source_type: str,
    source_id: str,
    parent_grant: Optional[PermissionGrant],
    request,
) -> GrantPermissionResult:
    """Inner write-only step of :func:`grant_permission`.

    All validation has already happened in the outer function — this is a
    pure write that creates the :class:`PermissionGrant` row plus the
    matching :class:`PermissionAuditLog` and ``access_control``
    :class:`AuditEvent`. Wrapping only the writes keeps the transaction
    minimal and safe to commit.
    """

    grant = PermissionGrant.objects.create(
        employee=employee,
        permission_code=permission_code,
        scope_type=scope_type,
        scope_id=scope_id or "",
        grant_mode=grant_mode,
        granted_by=granted_by,
        expires_at=expires_at,
        note=note or "",
        source_type=source_type,
        source_id=source_id or "",
        parent_grant=parent_grant,
    )

    audit = _record_audit(
        request=request,
        actor=granted_by,
        target=employee,
        action=(
            PermissionAuditLog.ACTION_DELEGATE_CREATED
            if source_type == PermissionGrant.SOURCE_DELEGATION
            else PermissionAuditLog.ACTION_GRANT_CREATED
        ),
        permission_code=permission_code,
        scope_type=scope_type,
        scope_id=scope_id,
        new_value={
            "grant_id": grant.id,
            "grant_mode": grant_mode,
            "expires_at": grant.expires_at.isoformat() if grant.expires_at else None,
            "source_type": source_type,
            "parent_grant_id": parent_grant.id if parent_grant else None,
        },
        note=note,
    )
    return GrantPermissionResult(grant=grant, audit=audit)


@transaction.atomic
def revoke_permission(
    grant: PermissionGrant,
    *,
    revoked_by=None,
    note: str = "",
    request=None,
) -> PermissionGrant:
    if grant.status == PermissionGrant.STATUS_REVOKED:
        return grant
    old = {
        "status": grant.status,
        "grant_mode": grant.grant_mode,
    }
    grant.status = PermissionGrant.STATUS_REVOKED
    grant.revoked_at = timezone.now()
    grant.revoked_by = revoked_by
    grant.save(update_fields=["status", "revoked_at", "revoked_by"])

    # Cascade-revoke any delegated children that trace back to this grant.
    for child in PermissionGrant.objects.filter(
        parent_grant=grant, status=PermissionGrant.STATUS_ACTIVE
    ):
        revoke_permission(child, revoked_by=revoked_by, note=f"cascade: {note}", request=request)

    _record_audit(
        request=request,
        actor=revoked_by,
        target=grant.employee,
        action=(
            PermissionAuditLog.ACTION_DELEGATE_REVOKED
            if grant.source_type == PermissionGrant.SOURCE_DELEGATION
            else PermissionAuditLog.ACTION_GRANT_REVOKED
        ),
        permission_code=grant.permission_code,
        scope_type=grant.scope_type,
        scope_id=grant.scope_id,
        old_value=old,
        new_value={"status": grant.status},
        note=note,
    )
    return grant


def _assert_delegation_allowed(
    *,
    delegator,
    permission_code: str,
    parent_grant: PermissionGrant,
    target_scope_type: str,
    target_scope_id: str,
    target_expires_at=None,
    target_grant_mode: str = PermissionGrant.GRANT_MODE_USE_ONLY,
) -> None:
    """Verify a delegation attempt is legal. Raises :class:`DelegationNotAllowed`
    when it isn't.

    The contract enforced here:

    * ``parent_grant`` belongs to the caller and is still alive (active status
      *and* not past ``expires_at``);
    * the parent was issued in ``use_and_delegate`` mode and the requested
      ``target_grant_mode`` is not stronger than that;
    * the permission code matches and is identical along the chain;
    * the requested scope is the same scope (when same type) or strictly
      narrower than the parent's scope;
    * the child's ``expires_at`` is not past the parent's ``expires_at``;
    * the chain depth respects the matching :class:`DelegationRule`.
    """

    now = timezone.now()

    if parent_grant.employee_id != getattr(delegator, "id", None):
        raise DelegationNotAllowed(
            "parent_grant does not belong to the delegator",
            reason="parent_not_owned",
        )
    if not parent_grant.is_active:
        raise DelegationNotAllowed(
            "parent_grant is not active",
            reason="parent_inactive",
        )
    if parent_grant.expires_at and parent_grant.expires_at <= now:
        raise DelegationNotAllowed(
            "parent_grant has expired",
            reason="parent_expired",
        )
    if parent_grant.grant_mode != PermissionGrant.GRANT_MODE_USE_AND_DELEGATE:
        raise DelegationNotAllowed(
            "parent_grant is not delegable (use_only)",
            reason="parent_use_only",
        )
    if (
        target_grant_mode == PermissionGrant.GRANT_MODE_USE_AND_DELEGATE
        and parent_grant.grant_mode != PermissionGrant.GRANT_MODE_USE_AND_DELEGATE
    ):
        # Defence-in-depth: a child with use_and_delegate cannot be stronger
        # than its parent's grant mode.
        raise DelegationNotAllowed(
            "child grant_mode cannot exceed parent's grant_mode",
            reason="mode_escalation",
        )
    if parent_grant.permission_code != permission_code:
        raise DelegationNotAllowed(
            "parent_grant does not cover this permission_code",
            reason="permission_mismatch",
        )

    # Child's expires_at must not outlive the parent's. ``None`` means "no
    # explicit expiration" and is only allowed if the parent is also unbounded.
    if parent_grant.expires_at is not None:
        if target_expires_at is None:
            raise DelegationNotAllowed(
                "Delegated grant must have expires_at <= parent's expires_at",
                reason="child_unbounded_vs_bounded",
            )
        if target_expires_at > parent_grant.expires_at:
            raise DelegationNotAllowed(
                "Delegated grant cannot outlive the parent grant",
                reason="child_outlives_parent",
            )

    # Target scope must be narrower-or-equal than parent's scope.
    if parent_grant.scope_type != SCOPE_GLOBAL:
        parent_breadth = SCOPE_BREADTH_ORDER.get(parent_grant.scope_type, 0)
        target_breadth = SCOPE_BREADTH_ORDER.get(target_scope_type, 0)
        if target_breadth < parent_breadth:
            raise DelegationNotAllowed(
                "Delegation target scope is broader than the parent grant",
                reason="scope_broader",
            )
        # Same scope type → ids must match
        if parent_grant.scope_type == target_scope_type and (
            parent_grant.scope_id or ""
        ) != (target_scope_id or ""):
            raise DelegationNotAllowed(
                "Delegation target scope id does not match the parent grant",
                reason="scope_id_mismatch",
            )

    # Enforce max depth using the parent chain.
    rule = DelegationRule.objects.filter(
        permission_code=permission_code,
        from_scope_type=parent_grant.scope_type,
        to_scope_type=target_scope_type,
    ).first()
    if rule is None:
        if parent_grant.scope_type != target_scope_type:
            raise DelegationNotAllowed(
                f"No delegation rule for {permission_code} "
                f"{parent_grant.scope_type}->{target_scope_type}",
                reason="no_delegation_rule",
            )
        return
    if not rule.allow_delegate:
        raise DelegationNotAllowed(
            f"Delegation disabled by rule for {permission_code}",
            reason="rule_disabled",
        )
    if rule.allow_same_scope_only and parent_grant.scope_type != target_scope_type:
        raise DelegationNotAllowed(
            "Rule only allows same-scope delegation",
            reason="rule_same_scope_only",
        )
    if rule.max_delegate_depth:
        depth = 1
        cur = parent_grant
        while cur.parent_grant_id:
            depth += 1
            cur = cur.parent_grant
            if depth > rule.max_delegate_depth:
                raise DelegationNotAllowed(
                    f"max_delegate_depth={rule.max_delegate_depth} exceeded",
                    reason="max_depth_exceeded",
                )


# ---------------------------------------------------------------------------
# Role templates
# ---------------------------------------------------------------------------


@dataclass
class AssignTemplateResult:
    assignment: RoleTemplateAssignment
    grants: list[PermissionGrant]
    audit: PermissionAuditLog


@transaction.atomic
def assign_role_template(
    *,
    employee,
    role_template: RoleTemplate,
    scope_type: str = "",
    scope_id: str = "",
    assigned_by=None,
    note: str = "",
    request=None,
) -> AssignTemplateResult:
    if not role_template.is_active:
        raise AccessControlError(f"RoleTemplate {role_template.code} is inactive")

    effective_scope_type = scope_type or role_template.default_scope_type

    assignment = RoleTemplateAssignment.objects.create(
        role_template=role_template,
        employee=employee,
        scope_type=effective_scope_type,
        scope_id=scope_id or "",
        assigned_by=assigned_by,
        note=note or "",
    )

    audit = _record_audit(
        request=request,
        actor=assigned_by,
        target=employee,
        action=PermissionAuditLog.ACTION_TEMPLATE_ASSIGNED,
        scope_type=effective_scope_type,
        scope_id=scope_id,
        new_value={
            "assignment_id": assignment.id,
            "role_template": role_template.code,
            "permissions": list(
                RoleTemplatePermission.objects.filter(
                    role_template=role_template, default_enabled=True
                ).values_list("permission_code", flat=True)
            ),
        },
        note=note,
    )

    return AssignTemplateResult(assignment=assignment, grants=[], audit=audit)


@transaction.atomic
def remove_role_template(
    assignment: RoleTemplateAssignment,
    *,
    actor=None,
    note: str = "",
    request=None,
) -> RoleTemplateAssignment:
    if not assignment.is_active:
        return assignment
    old = {
        "assignment_id": assignment.id,
        "role_template": assignment.role_template.code,
        "scope_type": assignment.scope_type,
        "scope_id": assignment.scope_id,
    }
    assignment.is_active = False
    assignment.revoked_at = timezone.now()
    assignment.save(update_fields=["is_active", "revoked_at"])

    _record_audit(
        request=request,
        actor=actor,
        target=assignment.employee,
        action=PermissionAuditLog.ACTION_TEMPLATE_REMOVED,
        scope_type=assignment.scope_type,
        scope_id=assignment.scope_id,
        old_value=old,
        new_value={"is_active": False},
        note=note,
    )
    return assignment


# ---------------------------------------------------------------------------
# Re-exports
# ---------------------------------------------------------------------------


# These are convenience re-exports so callers don't have to import from two
# modules just to answer "does this user have X?".
has_permission = resolver.has_permission
can_delegate = resolver.can_delegate
list_effective_permissions = resolver.list_effective_permissions
list_permission_sources = resolver.list_permission_sources


__all__ = (
    "AccessControlError",
    "UnknownPermission",
    "ScopeNotAllowed",
    "DelegationNotAllowed",
    "DELEGATION_BLOCK_REASONS",
    "GrantPermissionResult",
    "AssignTemplateResult",
    "grant_permission",
    "revoke_permission",
    "assign_role_template",
    "remove_role_template",
    "has_permission",
    "can_delegate",
    "list_effective_permissions",
    "list_permission_sources",
)
