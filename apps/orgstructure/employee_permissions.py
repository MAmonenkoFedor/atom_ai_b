"""Employee access helpers for ``resolve_access(scope_type="employee")``."""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from apps.access.models import PermissionGrant
from apps.organizations.models import OrganizationMember
from apps.orgstructure.models import OrgUnitMember

EMPLOYEE_SCOPE = "employee"
_PRIVILEGED_ROLE_CODES = frozenset({"admin", "company_admin", "super_admin", "executive", "ceo"})


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


def is_privileged_employee_viewer(user) -> bool:
    role_code = _user_role_code(user) or ""
    return role_code in _PRIVILEGED_ROLE_CODES


def _active_org_ids_for_user(user) -> set[int]:
    if not user or not getattr(user, "is_authenticated", False):
        return set()
    ids = OrganizationMember.objects.filter(user=user, is_active=True).values_list("organization_id", flat=True)
    return {int(v) for v in ids}


def shared_org_ids(viewer, employee) -> set[int]:
    return _active_org_ids_for_user(viewer) & _active_org_ids_for_user(employee)


def shared_department_ids(viewer, employee) -> set[int]:
    if not viewer or not getattr(viewer, "is_authenticated", False):
        return set()
    lhs = set(OrgUnitMember.objects.filter(user=viewer).values_list("org_unit_id", flat=True))
    rhs = set(OrgUnitMember.objects.filter(user=employee).values_list("org_unit_id", flat=True))
    return {int(v) for v in lhs & rhs}


def _has_scoped_permission(user, permission_code: str, scope_type: str, scope_id: str) -> bool:
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
            scope_type=scope_type,
            scope_id=scope_id,
        )
    except Exception:
        return False


def has_employee_scoped_permission(user, employee, permission_code: str) -> bool:
    """Employee policy permission in employee/company/department scopes."""
    if _has_scoped_permission(user, permission_code, EMPLOYEE_SCOPE, str(employee.pk)):
        return True
    for org_id in shared_org_ids(user, employee):
        if _has_scoped_permission(user, permission_code, "company", str(org_id)):
            return True
    for org_unit_id in shared_department_ids(user, employee):
        if _has_scoped_permission(user, permission_code, "department", str(org_unit_id)):
            return True
    return False


def _employee_ids_from_grants(user) -> set[int]:
    if not user or not getattr(user, "is_authenticated", False):
        return set()
    now = timezone.now()
    rows = (
        PermissionGrant.objects.filter(
            employee=user,
            scope_type=EMPLOYEE_SCOPE,
            status=PermissionGrant.STATUS_ACTIVE,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .values_list("scope_id", flat=True)
    )
    out: set[int] = set()
    for raw in rows:
        try:
            out.add(int(str(raw).strip()))
        except (TypeError, ValueError):
            continue
    return out


def apply_employee_list_visibility(qs, user):
    """Rough pre-filter for discoverable employees; policy is enforced per-row."""
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()
    if bool(getattr(user, "is_superuser", False)):
        return qs

    org_ids = _active_org_ids_for_user(user)
    if not org_ids:
        return qs.filter(pk=getattr(user, "pk", None))

    base = qs.filter(
        organization_memberships__is_active=True,
        organization_memberships__organization_id__in=org_ids,
    )
    if is_privileged_employee_viewer(user):
        return base.distinct()

    department_ids = OrgUnitMember.objects.filter(user=user).values_list("org_unit_id", flat=True)
    same_dept_user_ids = OrgUnitMember.objects.filter(org_unit_id__in=department_ids).values_list("user_id", flat=True)
    direct_employee_ids = _employee_ids_from_grants(user)
    return base.filter(
        Q(pk=user.pk) | Q(pk__in=same_dept_user_ids) | Q(pk__in=direct_employee_ids)
    ).distinct()


def compute_employee_policy_decision(viewer, employee):
    """Derive maximum access level for employee profile endpoints."""
    from apps.access.policies import PolicyDecision

    subject_id = int(getattr(viewer, "id", 0) or 0)
    sid = str(employee.pk)
    oid = int(employee.pk)

    if not viewer or not getattr(viewer, "is_authenticated", False):
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason="anonymous",
            scope_type="employee",
            scope_id=sid,
            subject_id=subject_id,
            object_id=oid,
        )

    if bool(getattr(viewer, "is_superuser", False)):
        return PolicyDecision(
            allowed=True,
            access_level="admin",
            reason="superuser",
            scope_type="employee",
            scope_id=sid,
            subject_id=subject_id,
            object_id=oid,
        )

    if int(getattr(viewer, "pk", 0) or 0) == oid:
        return PolicyDecision(
            allowed=True,
            access_level="read",
            reason="self",
            scope_type="employee",
            scope_id=sid,
            subject_id=subject_id,
            object_id=oid,
        )

    shared_orgs = shared_org_ids(viewer, employee)
    if not shared_orgs:
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason="no_shared_organization",
            scope_type="employee",
            scope_id=sid,
            subject_id=subject_id,
            object_id=oid,
        )

    if is_privileged_employee_viewer(viewer):
        return PolicyDecision(
            allowed=True,
            access_level="admin",
            reason="privileged_company_role",
            scope_type="employee",
            scope_id=sid,
            subject_id=subject_id,
            object_id=oid,
        )

    if has_employee_scoped_permission(viewer, employee, "employee.manage_roles"):
        return PolicyDecision(
            allowed=True,
            access_level="manage",
            reason="permission:employee.manage_roles",
            scope_type="employee",
            scope_id=sid,
            subject_id=subject_id,
            object_id=oid,
        )

    if has_employee_scoped_permission(viewer, employee, "employee.update"):
        return PolicyDecision(
            allowed=True,
            access_level="write",
            reason="permission:employee.update",
            scope_type="employee",
            scope_id=sid,
            subject_id=subject_id,
            object_id=oid,
        )

    if has_employee_scoped_permission(viewer, employee, "employee.read"):
        return PolicyDecision(
            allowed=True,
            access_level="read",
            reason="permission:employee.read",
            scope_type="employee",
            scope_id=sid,
            subject_id=subject_id,
            object_id=oid,
        )

    if shared_department_ids(viewer, employee):
        return PolicyDecision(
            allowed=True,
            access_level="read",
            reason="shared_department",
            scope_type="employee",
            scope_id=sid,
            subject_id=subject_id,
            object_id=oid,
        )

    if has_employee_scoped_permission(viewer, employee, "employee.view_metadata"):
        return PolicyDecision(
            allowed=True,
            access_level="metadata",
            reason="permission:employee.view_metadata",
            scope_type="employee",
            scope_id=sid,
            subject_id=subject_id,
            object_id=oid,
        )

    return PolicyDecision(
        allowed=False,
        access_level="none",
        reason="no_permission",
        scope_type="employee",
        scope_id=sid,
        subject_id=subject_id,
        object_id=oid,
    )
