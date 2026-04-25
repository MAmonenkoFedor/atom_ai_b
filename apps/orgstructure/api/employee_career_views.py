"""Employee career / lifecycle API.

Endpoints used by the Super Admin (and, for non-super-admin actions, Company Admin)
cabinet to manage an employee's system role, job title, department assignments,
project assignments, and line manager — and to view the resulting career timeline.

All mutating endpoints go through :mod:`apps.orgstructure.career_service` so that
every change writes both an :class:`EmployeeCareerEvent` and an ``AuditEvent``.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import (
    IsCompanyAdminOrSuperAdmin,
    IsSuperAdmin,
    normalized_roles_for_user,
)
from apps.identity.models import UserRole
from apps.organizations.models import Organization, OrganizationMember
from apps.orgstructure.career_service import (
    CareerContext,
    assign_to_department,
    assign_to_project,
    change_job_title,
    change_system_role,
    is_super_admin,
    remove_from_department,
    remove_from_project,
    set_line_manager,
    transfer_to_department,
)
from apps.orgstructure.models import (
    EmployeeCareerEvent,
    OrgUnit,
    OrgUnitMember,
    UserManagerLink,
)
from apps.projects.models import Project, ProjectMember

User = get_user_model()


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------


def _employee_organization(employee, actor) -> Organization:
    """Return the organization to operate within.

    * super admin without an org: we use the employee's primary membership.
    * company admin: must share an organization with the employee.
    * other callers: never allowed here (DRF permission will block).
    """

    actor_roles = normalized_roles_for_user(actor)
    employee_org_ids = list(
        OrganizationMember.objects.filter(user=employee, is_active=True).values_list(
            "organization_id", flat=True
        )
    )
    if not employee_org_ids:
        raise ValidationError({"detail": "Сотрудник не состоит в организации."})

    if "super_admin" in actor_roles:
        return Organization.objects.get(id=employee_org_ids[0])

    actor_org_ids = list(
        OrganizationMember.objects.filter(user=actor, is_active=True).values_list(
            "organization_id", flat=True
        )
    )
    shared = sorted(set(actor_org_ids) & set(employee_org_ids))
    if not shared:
        raise PermissionDenied("Сотрудник не принадлежит вашей организации.")
    return Organization.objects.get(id=shared[0])


def _serialize_employee_basic(user) -> dict:
    full = (user.get_full_name() or "").strip() or user.username
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "name": full,
    }


def _serialize_org_unit_assignment(m: OrgUnitMember) -> dict:
    return {
        "org_unit_id": str(m.org_unit_id),
        "org_unit_name": m.org_unit.name,
        "organization_id": str(m.org_unit.organization_id),
        "position": m.position,
        "is_lead": m.is_lead,
        "joined_at": m.joined_at.isoformat() if m.joined_at else None,
    }


def _serialize_project_assignment(m: ProjectMember) -> dict:
    return {
        "project_id": str(m.project_id),
        "project_name": m.project.name,
        "organization_id": str(m.project.organization_id),
        "project_role": m.role,
        "title_in_project": m.title_in_project,
        "engagement_weight": (
            float(m.engagement_weight) if m.engagement_weight is not None else None
        ),
        "is_active": m.is_active,
        "joined_at": m.joined_at.isoformat() if m.joined_at else None,
    }


def _serialize_career_event(ev: EmployeeCareerEvent) -> dict:
    actor = ev.actor
    return {
        "id": str(ev.id),
        "event_type": ev.event_type,
        "from_value": ev.from_value,
        "to_value": ev.to_value,
        "effective_from": ev.effective_from.isoformat() if ev.effective_from else None,
        "effective_to": ev.effective_to.isoformat() if ev.effective_to else None,
        "reason": ev.reason,
        "metadata": ev.metadata or {},
        "project_id": str(ev.project_id) if ev.project_id else "",
        "org_unit_id": str(ev.org_unit_id) if ev.org_unit_id else "",
        "organization_id": str(ev.organization_id) if ev.organization_id else "",
        "actor": _serialize_employee_basic(actor) if actor else None,
        "created_at": ev.created_at.isoformat() if ev.created_at else None,
    }


def _employee_snapshot(employee) -> dict:
    """Current assignments + job title + system role + manager."""

    org_units = list(
        OrgUnitMember.objects.select_related("org_unit", "org_unit__organization").filter(
            user=employee,
        )
    )
    projects = list(
        ProjectMember.objects.select_related("project", "project__organization").filter(
            user=employee,
        )
    )
    memberships = list(
        OrganizationMember.objects.select_related("organization").filter(
            user=employee, is_active=True
        )
    )
    manager_link = (
        UserManagerLink.objects.select_related("manager", "organization")
        .filter(employee=employee)
        .first()
    )
    role_assignment = UserRole.objects.select_related("role").filter(user=employee).first()
    return {
        "employee": _serialize_employee_basic(employee),
        "system_role": role_assignment.role.code if (role_assignment and role_assignment.role) else "",
        "is_protected_ceo": is_super_admin(employee),
        "job_titles": [
            {
                "organization_id": str(m.organization_id),
                "organization_name": m.organization.name,
                "job_title": m.job_title,
            }
            for m in memberships
        ],
        "department_assignments": [_serialize_org_unit_assignment(m) for m in org_units],
        "project_assignments": [_serialize_project_assignment(m) for m in projects],
        "line_manager": (
            {
                "organization_id": str(manager_link.organization_id),
                "manager": _serialize_employee_basic(manager_link.manager),
            }
            if manager_link
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class EmployeeCareerHistoryView(APIView):
    """``GET /api/employees/<user_id>/career`` — snapshot + timeline."""

    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    def get(self, request, user_id: int):
        employee = get_object_or_404(User, pk=user_id)
        _employee_organization(employee, request.user)
        limit = int(request.query_params.get("limit") or 100)
        limit = max(1, min(limit, 500))
        events = list(
            EmployeeCareerEvent.objects.select_related(
                "actor", "project", "org_unit", "organization"
            )
            .filter(employee=employee)
            .order_by("-effective_from", "-id")[:limit]
        )
        snapshot = _employee_snapshot(employee)
        return Response(
            {
                **snapshot,
                "events": [_serialize_career_event(ev) for ev in events],
            },
            status=status.HTTP_200_OK,
        )


class EmployeeJobTitleView(APIView):
    """``PATCH /api/employees/<user_id>/profile`` — job title and/or system role."""

    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    def patch(self, request, user_id: int):
        employee = get_object_or_404(User, pk=user_id)
        organization = _employee_organization(employee, request.user)
        ctx = CareerContext(
            actor=request.user,
            reason=str(request.data.get("reason") or ""),
            request=request,
        )
        events = []
        job_title = request.data.get("job_title")
        if job_title is not None:
            ev = change_job_title(
                employee=employee,
                organization=organization,
                new_job_title=str(job_title),
                ctx=ctx,
            )
            if ev:
                events.append(ev)

        system_role = request.data.get("system_role")
        if system_role is not None:
            actor_roles = normalized_roles_for_user(request.user)
            if system_role == "super_admin" and "super_admin" not in actor_roles:
                raise PermissionDenied("Только super admin может назначать system_role=super_admin.")
            try:
                ev = change_system_role(
                    employee=employee,
                    organization=organization,
                    new_role_code=str(system_role),
                    ctx=ctx,
                )
            except ValueError as exc:
                raise ValidationError({"system_role": str(exc)})
            if ev:
                events.append(ev)

        return Response(
            {
                **_employee_snapshot(employee),
                "events": [_serialize_career_event(ev) for ev in events],
            },
            status=status.HTTP_200_OK,
        )


class EmployeeDepartmentAssignmentsView(APIView):
    """``POST /api/employees/<user_id>/assignments/org-unit``.

    Body: ``{ org_unit_id, position?, is_lead?, mode?, reason? }``. ``mode`` may be
    ``assign`` (default) or ``transfer`` — transfer moves them away from other
    departments in the same organization first.
    """

    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    def post(self, request, user_id: int):
        employee = get_object_or_404(User, pk=user_id)
        organization = _employee_organization(employee, request.user)
        org_unit_id = request.data.get("org_unit_id")
        if not org_unit_id:
            raise ValidationError({"org_unit_id": "Поле обязательно."})
        org_unit = get_object_or_404(OrgUnit, pk=org_unit_id)
        if org_unit.organization_id != organization.id:
            raise PermissionDenied("Отдел принадлежит другой организации.")
        if not OrganizationMember.objects.filter(
            user=employee, organization=organization, is_active=True
        ).exists():
            raise ValidationError({"employee": "Сотрудник не в этой организации."})

        ctx = CareerContext(
            actor=request.user,
            reason=str(request.data.get("reason") or ""),
            request=request,
        )
        mode = (request.data.get("mode") or "assign").lower()
        position = str(request.data.get("position") or "")
        is_lead = bool(request.data.get("is_lead") or False)

        if mode == "transfer":
            events = transfer_to_department(
                employee=employee,
                target_org_unit=org_unit,
                position=position,
                is_lead=is_lead,
                ctx=ctx,
            )
        else:
            events = assign_to_department(
                employee=employee,
                org_unit=org_unit,
                position=position,
                is_lead=is_lead,
                ctx=ctx,
            )

        return Response(
            {
                **_employee_snapshot(employee),
                "events": [_serialize_career_event(ev) for ev in events],
            },
            status=status.HTTP_200_OK,
        )


class EmployeeDepartmentAssignmentDetailView(APIView):
    """``DELETE /api/employees/<user_id>/assignments/org-unit/<int:ou_id>``."""

    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    def delete(self, request, user_id: int, org_unit_id: int):
        employee = get_object_or_404(User, pk=user_id)
        org_unit = get_object_or_404(OrgUnit, pk=org_unit_id)
        organization = _employee_organization(employee, request.user)
        if org_unit.organization_id != organization.id:
            raise PermissionDenied("Отдел принадлежит другой организации.")
        ctx = CareerContext(
            actor=request.user,
            reason=str(request.data.get("reason") or ""),
            request=request,
        )
        events = remove_from_department(
            employee=employee,
            org_unit=org_unit,
            ctx=ctx,
        )
        return Response(
            {
                **_employee_snapshot(employee),
                "events": [_serialize_career_event(ev) for ev in events],
            },
            status=status.HTTP_200_OK,
        )


class EmployeeProjectAssignmentsView(APIView):
    """``POST /api/employees/<user_id>/assignments/project`` — assign or update."""

    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    def post(self, request, user_id: int):
        employee = get_object_or_404(User, pk=user_id)
        organization = _employee_organization(employee, request.user)
        project_id = request.data.get("project_id")
        if not project_id:
            raise ValidationError({"project_id": "Поле обязательно."})
        project = get_object_or_404(Project, pk=project_id)
        if project.organization_id != organization.id:
            raise PermissionDenied("Проект принадлежит другой организации.")
        if not OrganizationMember.objects.filter(
            user=employee, organization=organization, is_active=True
        ).exists():
            raise ValidationError({"employee": "Сотрудник не в этой организации."})

        project_role = str(request.data.get("project_role") or ProjectMember.ROLE_CONTRIBUTOR)
        if project_role not in dict(ProjectMember.ROLE_CHOICES):
            raise ValidationError({"project_role": "Недопустимая роль."})

        ctx = CareerContext(
            actor=request.user,
            reason=str(request.data.get("reason") or ""),
            request=request,
        )
        events = assign_to_project(
            employee=employee,
            project=project,
            project_role=project_role,
            title_in_project=str(request.data.get("title_in_project") or ""),
            engagement_weight=request.data.get("engagement_weight"),
            ctx=ctx,
        )
        return Response(
            {
                **_employee_snapshot(employee),
                "events": [_serialize_career_event(ev) for ev in events],
            },
            status=status.HTTP_200_OK,
        )


class EmployeeProjectAssignmentDetailView(APIView):
    """``DELETE /api/employees/<user_id>/assignments/project/<int:project_id>``."""

    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    def delete(self, request, user_id: int, project_id: int):
        employee = get_object_or_404(User, pk=user_id)
        project = get_object_or_404(Project, pk=project_id)
        organization = _employee_organization(employee, request.user)
        if project.organization_id != organization.id:
            raise PermissionDenied("Проект принадлежит другой организации.")
        ctx = CareerContext(
            actor=request.user,
            reason=str(request.data.get("reason") or ""),
            request=request,
        )
        events = remove_from_project(
            employee=employee,
            project=project,
            ctx=ctx,
        )
        return Response(
            {
                **_employee_snapshot(employee),
                "events": [_serialize_career_event(ev) for ev in events],
            },
            status=status.HTTP_200_OK,
        )


class EmployeeLineManagerView(APIView):
    """``PUT /api/employees/<user_id>/assignments/manager`` — set or clear manager."""

    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    def put(self, request, user_id: int):
        employee = get_object_or_404(User, pk=user_id)
        organization = _employee_organization(employee, request.user)
        manager_id = request.data.get("manager_id")
        manager = None
        if manager_id:
            manager = get_object_or_404(User, pk=manager_id)
            if not OrganizationMember.objects.filter(
                user=manager, organization=organization, is_active=True
            ).exists():
                raise ValidationError({"manager_id": "Руководитель не в этой организации."})
            if manager.id == employee.id:
                raise ValidationError({"manager_id": "Нельзя назначить сотрудника руководителем самому себе."})
        ctx = CareerContext(
            actor=request.user,
            reason=str(request.data.get("reason") or ""),
            request=request,
        )
        ev = set_line_manager(
            employee=employee,
            organization=organization,
            manager=manager,
            ctx=ctx,
        )
        return Response(
            {
                **_employee_snapshot(employee),
                "events": [_serialize_career_event(ev)] if ev else [],
            },
            status=status.HTTP_200_OK,
        )
