"""Department (OrgUnit) access helpers and policy ladder for ``resolve_access``."""

from __future__ import annotations

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.access.models import PermissionGrant, SCOPE_DEPARTMENT
from apps.core.api.permissions import normalized_roles_for_user
from apps.organizations.models import OrganizationMember
from apps.orgstructure.models import OrgUnit, OrgUnitMember

DEPARTMENT_SCOPE = SCOPE_DEPARTMENT


def _user_role_code(user) -> str | None:
    if not user or not getattr(user, "is_authenticated", False):
        return None
    assignments = getattr(user, "role_assignments", None)
    if assignments is None:
        return None
    assignment = assignments.select_related("role").first()
    if not assignment or not getattr(assignment, "role", None):
        return None
    return assignment.role.code


def is_privileged_department_viewer(user) -> bool:
    """Same executive / admin envelope as project list (company-wide visibility)."""

    role_code = _user_role_code(user) or ""
    return role_code in {"admin", "company_admin", "super_admin", "executive", "ceo"}


def get_department_membership(user, org_unit: OrgUnit) -> OrgUnitMember | None:
    if not user or not getattr(user, "is_authenticated", False):
        return None
    return OrgUnitMember.objects.filter(user=user, org_unit=org_unit).first()


def _department_ids_from_grants(user) -> list[int]:
    if not user or not getattr(user, "is_authenticated", False):
        return []
    try:
        now = timezone.now()
        raw_ids = (
            PermissionGrant.objects.filter(
                employee=user,
                scope_type=DEPARTMENT_SCOPE,
                status=PermissionGrant.STATUS_ACTIVE,
            )
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .values_list("scope_id", flat=True)
        )
        out: list[int] = []
        for sid in raw_ids:
            try:
                out.append(int(str(sid).strip()))
            except (TypeError, ValueError):
                continue
        return out
    except Exception:
        return []


def has_department_access_permission(user, org_unit: OrgUnit, permission_code: str) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    try:
        from apps.access.resolver import has_permission
    except Exception:
        return False
    try:
        return has_permission(
            user=user,
            permission_code=permission_code,
            scope_type=DEPARTMENT_SCOPE,
            scope_id=str(org_unit.pk),
        )
    except Exception:
        return False


def can_manage_department(user, org_unit: OrgUnit) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    m = get_department_membership(user, org_unit)
    if m and m.is_lead:
        return True
    roles = normalized_roles_for_user(user)
    if "company_admin" in roles and OrganizationMember.objects.filter(
        user=user, organization=org_unit.organization, is_active=True
    ).exists():
        return True
    if has_department_access_permission(user, org_unit, "department.edit"):
        return True
    if has_department_access_permission(user, org_unit, "department.manage_workspace"):
        return True
    return False


def can_department_action(user, org_unit: OrgUnit, permission_code: str, *, legacy_manage: bool = True) -> bool:
    if has_department_access_permission(user, org_unit, permission_code):
        return True
    return bool(legacy_manage and can_manage_department(user, org_unit))


def apply_department_list_visibility(qs, user):
    """Departments the user may discover (metadata list and detail routing)."""

    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()

    org_ids = list(
        OrganizationMember.objects.filter(user=user, is_active=True).values_list(
            "organization_id", flat=True
        )
    )

    if is_privileged_department_viewer(user):
        if not org_ids:
            return qs.none()
        return qs.filter(organization_id__in=org_ids)

    combined = set(OrgUnitMember.objects.filter(user=user).values_list("org_unit_id", flat=True))
    combined.update(_department_ids_from_grants(user))
    if not combined:
        return qs.none()
    return qs.filter(pk__in=combined)


def compute_department_policy_decision(user, org_unit: OrgUnit):
    """Derive maximum department access level for ``resolve_access`` / audits."""

    from apps.access.policies import PolicyDecision

    subject_id = int(getattr(user, "id", 0) or 0)
    sid = str(org_unit.pk)
    object_id = int(org_unit.pk)
    org = org_unit.organization

    if not user or not getattr(user, "is_authenticated", False):
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason="anonymous",
            scope_type="department",
            scope_id=sid,
            subject_id=subject_id,
            object_id=object_id,
        )

    if bool(getattr(user, "is_superuser", False)):
        return PolicyDecision(
            allowed=True,
            access_level="admin",
            reason="superuser",
            scope_type="department",
            scope_id=sid,
            subject_id=subject_id,
            object_id=object_id,
        )

    if is_privileged_department_viewer(user) and OrganizationMember.objects.filter(
        user=user, organization=org, is_active=True
    ).exists():
        return PolicyDecision(
            allowed=True,
            access_level="admin",
            reason="privileged_company_role",
            scope_type="department",
            scope_id=sid,
            subject_id=subject_id,
            object_id=object_id,
        )

    if can_manage_department(user, org_unit):
        return PolicyDecision(
            allowed=True,
            access_level="manage",
            reason="department_manage",
            scope_type="department",
            scope_id=sid,
            subject_id=subject_id,
            object_id=object_id,
        )

    if can_department_action(user, org_unit, "department.update", legacy_manage=True):
        return PolicyDecision(
            allowed=True,
            access_level="write",
            reason="permission:department.update",
            scope_type="department",
            scope_id=sid,
            subject_id=subject_id,
            object_id=object_id,
        )

    if get_department_membership(user, org_unit) is not None:
        return PolicyDecision(
            allowed=True,
            access_level="read",
            reason="department_membership",
            scope_type="department",
            scope_id=sid,
            subject_id=subject_id,
            object_id=object_id,
        )

    if has_department_access_permission(user, org_unit, "department.read"):
        return PolicyDecision(
            allowed=True,
            access_level="read",
            reason="permission:department.read",
            scope_type="department",
            scope_id=sid,
            subject_id=subject_id,
            object_id=object_id,
        )

    if has_department_access_permission(user, org_unit, "department.view_metadata"):
        return PolicyDecision(
            allowed=True,
            access_level="metadata",
            reason="permission:department.view_metadata",
            scope_type="department",
            scope_id=sid,
            subject_id=subject_id,
            object_id=object_id,
        )

    return PolicyDecision(
        allowed=False,
        access_level="none",
        reason="no_permission",
        scope_type="department",
        scope_id=sid,
        subject_id=subject_id,
        object_id=object_id,
    )


def require_view_department(user, org_unit: OrgUnit):
    """Gate department detail: ``department.read`` or ``department.view_metadata``."""

    from apps.access.policies import resolve_access

    d = resolve_access(
        user=user,
        action="department.read",
        scope_type="department",
        scope_id=str(org_unit.pk),
        resource=org_unit,
    )
    if d.allowed:
        return d
    d2 = resolve_access(
        user=user,
        action="department.view_metadata",
        scope_type="department",
        scope_id=str(org_unit.pk),
        resource=org_unit,
    )
    if not d2.allowed:
        raise PermissionDenied("You do not have access to this department.")
    return d2


def require_department_access(user, org_unit: OrgUnit, action: str, message: str):
    from apps.access.policies import resolve_access

    d = resolve_access(
        user=user,
        action=action,
        scope_type="department",
        scope_id=str(org_unit.pk),
        resource=org_unit,
    )
    if not d.allowed:
        raise PermissionDenied(message)
    return d

