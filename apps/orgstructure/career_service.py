"""Employee career service.

Single entry point for all changes to an employee's assignments (department / project /
job title / system role). Every mutation:

1. Updates the *current state* record (`OrganizationMember`, `OrgUnitMember`,
   `ProjectMember`, or the user's system role assignment).
2. Appends an `EmployeeCareerEvent` so the history is preserved forever.
3. Optionally emits an audit event (when called from a view with an HTTP request).

Views / serializers should never mutate these tables directly — they should call the
helpers here so history and audit stay in sync.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.audit.service import emit_audit_event
from apps.organizations.models import Organization, OrganizationMember
from apps.orgstructure.models import (
    EmployeeCareerEvent,
    OrgUnit,
    OrgUnitMember,
    UserManagerLink,
)
from apps.projects.models import Project, ProjectMember


# ---------------------------------------------------------------------------
# CEO / super admin protection
# ---------------------------------------------------------------------------
#
# The super_admin user ("CEO") is considered immutable from the career /
# lifecycle perspective: no one — not even another super_admin — can change
# their system role, department, project assignments, or line manager via
# these admin tools. They always own a separate cabinet.


def is_super_admin(user) -> bool:
    """Return True if *user* currently holds the ``super_admin`` role."""

    if user is None:
        return False
    from apps.identity.models import UserRole

    return UserRole.objects.filter(user=user, role__code="super_admin").exists()


def ensure_mutable_employee(employee) -> None:
    """Guard that prevents mutations on a protected CEO account."""

    if is_super_admin(employee):
        raise PermissionDenied(
            "Суперадмин (CEO) защищён от карьерных изменений: его нельзя "
            "переназначать, переводить или менять роль через этот инструмент."
        )


@dataclass
class CareerContext:
    """Context passed around when a change is recorded.

    * ``actor`` — who performed the change (super admin, company admin, system).
    * ``reason`` — optional human-readable reason (e.g. "promoted after Q2 review").
    * ``request`` — HTTP request for audit emission. Optional (e.g. system jobs).
    """

    actor: Any = None
    reason: str = ""
    request: Any = None


def _emit_event(
    *,
    employee,
    organization: Optional[Organization],
    event_type: str,
    from_value: str = "",
    to_value: str = "",
    project: Optional[Project] = None,
    org_unit: Optional[OrgUnit] = None,
    metadata: Optional[dict] = None,
    ctx: Optional[CareerContext] = None,
) -> EmployeeCareerEvent:
    ctx = ctx or CareerContext()
    event = EmployeeCareerEvent.objects.create(
        employee=employee,
        organization=organization,
        event_type=event_type,
        from_value=from_value or "",
        to_value=to_value or "",
        effective_from=timezone.now(),
        actor=ctx.actor if (ctx.actor and getattr(ctx.actor, "is_authenticated", False)) else None,
        reason=ctx.reason or "",
        metadata=metadata or {},
        project=project,
        org_unit=org_unit,
    )
    if ctx.request is not None:
        try:
            emit_audit_event(
                ctx.request,
                event_type=f"career.{event_type}",
                entity_type="employee",
                action=event_type,
                entity_id=str(employee.id),
                project_id=str(project.id) if project else "",
                payload={
                    "from": from_value,
                    "to": to_value,
                    "org_unit_id": str(org_unit.id) if org_unit else "",
                    "reason": ctx.reason or "",
                },
            )
        except Exception:
            # Audit failure must not break career mutation.
            pass
    return event


def _close_prior_events(
    *,
    employee,
    event_types: Iterable[str],
    scope_filter: Optional[dict] = None,
) -> None:
    """Close (set ``effective_to``) open events of given types for an employee.

    Useful when we know an ongoing relationship has ended (e.g. former department
    lead event should be marked as ending when they step down).
    """

    qs = EmployeeCareerEvent.objects.filter(
        employee=employee,
        event_type__in=list(event_types),
        effective_to__isnull=True,
    )
    if scope_filter:
        qs = qs.filter(**scope_filter)
    qs.update(effective_to=timezone.now())


# ---------------------------------------------------------------------------
# Job title / organization membership
# ---------------------------------------------------------------------------


@transaction.atomic
def change_job_title(
    *,
    employee,
    organization: Organization,
    new_job_title: str,
    ctx: Optional[CareerContext] = None,
) -> EmployeeCareerEvent | None:
    ensure_mutable_employee(employee)
    membership, _ = OrganizationMember.objects.get_or_create(
        organization=organization,
        user=employee,
        defaults={"job_title": new_job_title or "", "is_active": True},
    )
    previous = membership.job_title or ""
    if previous == (new_job_title or ""):
        return None
    membership.job_title = new_job_title or ""
    membership.save(update_fields=["job_title"])
    return _emit_event(
        employee=employee,
        organization=organization,
        event_type=EmployeeCareerEvent.EVENT_JOB_TITLE_CHANGED,
        from_value=previous,
        to_value=new_job_title or "",
        ctx=ctx,
    )


# ---------------------------------------------------------------------------
# System role (platform access level)
# ---------------------------------------------------------------------------


@transaction.atomic
def change_system_role(
    *,
    employee,
    organization: Optional[Organization],
    new_role_code: str,
    ctx: Optional[CareerContext] = None,
) -> EmployeeCareerEvent | None:
    """Change the user's system role.

    We rewrite the primary role assignment on the user (identity app). The legacy
    seed data uses a single active ``UserRoleAssignment`` per user; we replace its
    role or create a new assignment.

    CEO protection: the super_admin role is immutable — we never demote a
    super_admin through this service. Only manual DB operations can change it.
    """

    from apps.identity.models import Role, UserRole

    # Protect an existing super_admin from being demoted / altered.
    if is_super_admin(employee) and new_role_code != "super_admin":
        raise PermissionDenied(
            "Суперадмина (CEO) нельзя понизить через инструмент карьеры."
        )

    new_role = Role.objects.filter(code=new_role_code).first()
    if not new_role:
        raise ValueError(f"Unknown system role: {new_role_code}")

    assignment = (
        UserRole.objects.select_related("role").filter(user=employee).first()
    )
    previous_code = assignment.role.code if (assignment and assignment.role) else ""
    if previous_code == new_role.code:
        return None

    if assignment:
        assignment.role = new_role
        assignment.save(update_fields=["role"])
    else:
        UserRole.objects.create(
            user=employee,
            role=new_role,
            organization=organization,
        )

    return _emit_event(
        employee=employee,
        organization=organization,
        event_type=EmployeeCareerEvent.EVENT_SYSTEM_ROLE_CHANGED,
        from_value=previous_code,
        to_value=new_role.code,
        ctx=ctx,
    )


# ---------------------------------------------------------------------------
# Department (OrgUnit)
# ---------------------------------------------------------------------------


@transaction.atomic
def assign_to_department(
    *,
    employee,
    org_unit: OrgUnit,
    position: str = "",
    is_lead: bool = False,
    ctx: Optional[CareerContext] = None,
) -> list[EmployeeCareerEvent]:
    """Add or update a department assignment. Emits the relevant career events."""

    ensure_mutable_employee(employee)
    ctx = ctx or CareerContext()
    events: list[EmployeeCareerEvent] = []
    organization = org_unit.organization

    membership = OrgUnitMember.objects.filter(
        user=employee,
        org_unit=org_unit,
    ).first()

    if membership is None:
        membership = OrgUnitMember.objects.create(
            user=employee,
            org_unit=org_unit,
            position=position or "",
            is_lead=bool(is_lead),
            assigned_by=ctx.actor if (ctx.actor and getattr(ctx.actor, "is_authenticated", False)) else None,
        )
        events.append(
            _emit_event(
                employee=employee,
                organization=organization,
                event_type=EmployeeCareerEvent.EVENT_JOINED_DEPARTMENT,
                to_value=org_unit.name,
                org_unit=org_unit,
                metadata={"position": position or "", "is_lead": bool(is_lead)},
                ctx=ctx,
            )
        )
        if is_lead:
            events.append(
                _emit_event(
                    employee=employee,
                    organization=organization,
                    event_type=EmployeeCareerEvent.EVENT_BECAME_DEPARTMENT_LEAD,
                    to_value=org_unit.name,
                    org_unit=org_unit,
                    ctx=ctx,
                )
            )
    else:
        changed_fields: list[str] = []
        previous_position = membership.position or ""
        previous_is_lead = bool(membership.is_lead)
        if position and position != previous_position:
            membership.position = position
            changed_fields.append("position")
            events.append(
                _emit_event(
                    employee=employee,
                    organization=organization,
                    event_type=EmployeeCareerEvent.EVENT_POSITION_CHANGED,
                    from_value=previous_position,
                    to_value=position,
                    org_unit=org_unit,
                    ctx=ctx,
                )
            )
        if bool(is_lead) != previous_is_lead:
            membership.is_lead = bool(is_lead)
            changed_fields.append("is_lead")
            events.append(
                _emit_event(
                    employee=employee,
                    organization=organization,
                    event_type=(
                        EmployeeCareerEvent.EVENT_BECAME_DEPARTMENT_LEAD
                        if is_lead
                        else EmployeeCareerEvent.EVENT_REMOVED_AS_DEPARTMENT_LEAD
                    ),
                    from_value=str(previous_is_lead).lower(),
                    to_value=str(bool(is_lead)).lower(),
                    org_unit=org_unit,
                    ctx=ctx,
                )
            )
            if not is_lead:
                _close_prior_events(
                    employee=employee,
                    event_types=[EmployeeCareerEvent.EVENT_BECAME_DEPARTMENT_LEAD],
                    scope_filter={"org_unit": org_unit},
                )
        if changed_fields:
            membership.save(update_fields=changed_fields)
    return events


@transaction.atomic
def transfer_to_department(
    *,
    employee,
    target_org_unit: OrgUnit,
    position: str = "",
    is_lead: bool = False,
    ctx: Optional[CareerContext] = None,
) -> list[EmployeeCareerEvent]:
    """Move employee from any currently-active department to ``target_org_unit``.

    If the employee already belongs to other departments in the same organization,
    each is closed with a ``left_department`` event. The final state is a single
    membership in ``target_org_unit``.
    """

    ensure_mutable_employee(employee)
    ctx = ctx or CareerContext()
    events: list[EmployeeCareerEvent] = []
    organization = target_org_unit.organization

    current_memberships = list(
        OrgUnitMember.objects.select_related("org_unit").filter(
            user=employee,
            org_unit__organization=organization,
        ).exclude(org_unit=target_org_unit)
    )
    for membership in current_memberships:
        events.extend(
            remove_from_department(
                employee=employee,
                org_unit=membership.org_unit,
                ctx=ctx,
            )
        )

    events.extend(
        assign_to_department(
            employee=employee,
            org_unit=target_org_unit,
            position=position,
            is_lead=is_lead,
            ctx=ctx,
        )
    )

    if current_memberships:
        events.append(
            _emit_event(
                employee=employee,
                organization=organization,
                event_type=EmployeeCareerEvent.EVENT_TRANSFERRED_DEPARTMENT,
                from_value=", ".join(m.org_unit.name for m in current_memberships),
                to_value=target_org_unit.name,
                org_unit=target_org_unit,
                ctx=ctx,
            )
        )

    return events


@transaction.atomic
def remove_from_department(
    *,
    employee,
    org_unit: OrgUnit,
    ctx: Optional[CareerContext] = None,
) -> list[EmployeeCareerEvent]:
    ensure_mutable_employee(employee)
    events: list[EmployeeCareerEvent] = []
    membership = OrgUnitMember.objects.filter(user=employee, org_unit=org_unit).first()
    if membership is None:
        return events

    organization = org_unit.organization
    was_lead = bool(membership.is_lead)
    membership.delete()

    if was_lead:
        events.append(
            _emit_event(
                employee=employee,
                organization=organization,
                event_type=EmployeeCareerEvent.EVENT_REMOVED_AS_DEPARTMENT_LEAD,
                from_value=org_unit.name,
                org_unit=org_unit,
                ctx=ctx,
            )
        )
        _close_prior_events(
            employee=employee,
            event_types=[EmployeeCareerEvent.EVENT_BECAME_DEPARTMENT_LEAD],
            scope_filter={"org_unit": org_unit},
        )

    events.append(
        _emit_event(
            employee=employee,
            organization=organization,
            event_type=EmployeeCareerEvent.EVENT_LEFT_DEPARTMENT,
            from_value=org_unit.name,
            org_unit=org_unit,
            ctx=ctx,
        )
    )
    _close_prior_events(
        employee=employee,
        event_types=[EmployeeCareerEvent.EVENT_JOINED_DEPARTMENT],
        scope_filter={"org_unit": org_unit},
    )
    return events


# ---------------------------------------------------------------------------
# Line manager
# ---------------------------------------------------------------------------


@transaction.atomic
def set_line_manager(
    *,
    employee,
    organization: Organization,
    manager,
    ctx: Optional[CareerContext] = None,
) -> EmployeeCareerEvent | None:
    ensure_mutable_employee(employee)
    link = UserManagerLink.objects.filter(organization=organization, employee=employee).first()
    previous_label = ""
    if link:
        previous_manager = link.manager
        previous_label = previous_manager.get_full_name() or previous_manager.username or str(previous_manager.id)
        if manager is None:
            link.delete()
        elif manager.id != link.manager_id:
            link.manager = manager
            link.save(update_fields=["manager"])
        else:
            return None
    else:
        if manager is None:
            return None
        UserManagerLink.objects.create(
            organization=organization,
            employee=employee,
            manager=manager,
        )

    to_label = ""
    if manager is not None:
        to_label = manager.get_full_name() or manager.username or str(manager.id)

    return _emit_event(
        employee=employee,
        organization=organization,
        event_type=EmployeeCareerEvent.EVENT_MANAGER_CHANGED,
        from_value=previous_label,
        to_value=to_label,
        ctx=ctx,
    )


# ---------------------------------------------------------------------------
# Project assignment
# ---------------------------------------------------------------------------


@transaction.atomic
def assign_to_project(
    *,
    employee,
    project: Project,
    project_role: str = ProjectMember.ROLE_CONTRIBUTOR,
    title_in_project: str = "",
    engagement_weight=None,
    ctx: Optional[CareerContext] = None,
) -> list[EmployeeCareerEvent]:
    """Assign / update an employee's role in a project."""

    ensure_mutable_employee(employee)
    ctx = ctx or CareerContext()
    events: list[EmployeeCareerEvent] = []
    organization = project.organization

    member = ProjectMember.objects.filter(project=project, user=employee).first()
    if member is None:
        ProjectMember.objects.create(
            project=project,
            user=employee,
            role=project_role or ProjectMember.ROLE_CONTRIBUTOR,
            title_in_project=title_in_project or "",
            engagement_weight=engagement_weight,
            is_active=True,
            assigned_by=ctx.actor if (ctx.actor and getattr(ctx.actor, "is_authenticated", False)) else None,
        )
        events.append(
            _emit_event(
                employee=employee,
                organization=organization,
                event_type=EmployeeCareerEvent.EVENT_ASSIGNED_TO_PROJECT,
                to_value=project.name,
                project=project,
                metadata={
                    "project_role": project_role,
                    "title_in_project": title_in_project,
                },
                ctx=ctx,
            )
        )
        if project_role == ProjectMember.ROLE_LEAD:
            events.append(
                _emit_event(
                    employee=employee,
                    organization=organization,
                    event_type=EmployeeCareerEvent.EVENT_BECAME_PROJECT_LEAD,
                    to_value=project.name,
                    project=project,
                    ctx=ctx,
                )
            )
    else:
        changed_fields: list[str] = []
        prev_role = member.role
        prev_title = member.title_in_project or ""
        if project_role and project_role != prev_role:
            member.role = project_role
            changed_fields.append("role")
            events.append(
                _emit_event(
                    employee=employee,
                    organization=organization,
                    event_type=EmployeeCareerEvent.EVENT_PROJECT_ROLE_CHANGED,
                    from_value=prev_role,
                    to_value=project_role,
                    project=project,
                    ctx=ctx,
                )
            )
            if project_role == ProjectMember.ROLE_LEAD and prev_role != ProjectMember.ROLE_LEAD:
                events.append(
                    _emit_event(
                        employee=employee,
                        organization=organization,
                        event_type=EmployeeCareerEvent.EVENT_BECAME_PROJECT_LEAD,
                        to_value=project.name,
                        project=project,
                        ctx=ctx,
                    )
                )
            if prev_role == ProjectMember.ROLE_LEAD and project_role != ProjectMember.ROLE_LEAD:
                events.append(
                    _emit_event(
                        employee=employee,
                        organization=organization,
                        event_type=EmployeeCareerEvent.EVENT_REMOVED_AS_PROJECT_LEAD,
                        from_value=project.name,
                        project=project,
                        ctx=ctx,
                    )
                )
                _close_prior_events(
                    employee=employee,
                    event_types=[EmployeeCareerEvent.EVENT_BECAME_PROJECT_LEAD],
                    scope_filter={"project": project},
                )
        if title_in_project and title_in_project != prev_title:
            member.title_in_project = title_in_project
            changed_fields.append("title_in_project")
        if engagement_weight is not None and engagement_weight != member.engagement_weight:
            member.engagement_weight = engagement_weight
            changed_fields.append("engagement_weight")
        if not member.is_active:
            member.is_active = True
            changed_fields.append("is_active")
        if changed_fields:
            member.save(update_fields=changed_fields)

    return events


@transaction.atomic
def remove_from_project(
    *,
    employee,
    project: Project,
    ctx: Optional[CareerContext] = None,
) -> list[EmployeeCareerEvent]:
    ensure_mutable_employee(employee)
    events: list[EmployeeCareerEvent] = []
    member = ProjectMember.objects.filter(project=project, user=employee).first()
    if member is None:
        return events

    organization = project.organization
    was_lead = member.role == ProjectMember.ROLE_LEAD or getattr(member, "is_lead", False)
    member.delete()

    if was_lead:
        events.append(
            _emit_event(
                employee=employee,
                organization=organization,
                event_type=EmployeeCareerEvent.EVENT_REMOVED_AS_PROJECT_LEAD,
                from_value=project.name,
                project=project,
                ctx=ctx,
            )
        )
        _close_prior_events(
            employee=employee,
            event_types=[EmployeeCareerEvent.EVENT_BECAME_PROJECT_LEAD],
            scope_filter={"project": project},
        )

    events.append(
        _emit_event(
            employee=employee,
            organization=organization,
            event_type=EmployeeCareerEvent.EVENT_REMOVED_FROM_PROJECT,
            from_value=project.name,
            project=project,
            ctx=ctx,
        )
    )
    _close_prior_events(
        employee=employee,
        event_types=[EmployeeCareerEvent.EVENT_ASSIGNED_TO_PROJECT],
        scope_filter={"project": project},
    )
    return events
