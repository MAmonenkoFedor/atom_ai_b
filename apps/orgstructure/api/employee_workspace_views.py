"""Employee profile/workspace foundation (`/api/v1/employees/*`)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access import service as access_service
from apps.access.models import PermissionGrant
from apps.access.policies import policy_audit_payload, resolve_access
from apps.audit.service import emit_audit_event
from apps.core.api.permissions import normalized_roles_for_user
from apps.identity.models import Role, UserRole
from apps.organizations.models import Organization, OrganizationMember
from apps.orgstructure.career_service import CareerContext, change_job_title, change_system_role
from apps.orgstructure.employee_permissions import apply_employee_list_visibility, shared_org_ids
from apps.orgstructure.models import OrgUnitMember
from apps.projects.models import ProjectMember

from .employee_workspace_serializers import (
    EmployeeDepartmentSerializer,
    EmployeeDetailSerializer,
    EmployeeListItemSerializer,
    EmployeePatchSerializer,
    EmployeePermissionGrantCreateSerializer,
    EmployeePermissionGrantRevokeSerializer,
    EmployeePermissionGrantSerializer,
    EmployeeProjectSerializer,
    EmployeeRoleSerializer,
    EmployeeRoleUpdateSerializer,
    EmployeeWorkspaceSerializer,
)

User = get_user_model()


def _employee_base_queryset():
    return User.objects.filter(organization_memberships__is_active=True).distinct()


def _job_title_for(viewer, employee) -> str:
    org_ids = set(
        OrganizationMember.objects.filter(user=viewer, is_active=True).values_list("organization_id", flat=True)
    )
    row = (
        OrganizationMember.objects.filter(
            user=employee,
            is_active=True,
            organization_id__in=org_ids,
        )
        .order_by("organization_id")
        .first()
    )
    return (row.job_title or "").strip() if row else ""


def _employee_detail_payload(employee, *, access_level: str, read_allowed: bool, viewer) -> dict:
    full_name = (employee.get_full_name() or "").strip() or employee.username
    orgs = (
        OrganizationMember.objects.select_related("organization")
        .filter(user=employee, is_active=True)
        .order_by("organization_id")
    )
    return {
        "id": employee.id,
        "username": employee.username or "",
        "first_name": (employee.first_name or "") if read_allowed else "",
        "last_name": (employee.last_name or "") if read_allowed else "",
        "full_name": full_name,
        "email": (employee.email or "") if read_allowed else "",
        "access_level": access_level,
        "organizations": [
            {
                "organization_id": m.organization_id,
                "organization_name": m.organization.name,
                "job_title": (m.job_title or "") if read_allowed else "",
            }
            for m in orgs
        ],
        "viewer_job_title": _job_title_for(viewer, employee) if read_allowed else "",
    }


def _require_employee_metadata_or_read(request_user, employee):
    read_d = resolve_access(
        user=request_user,
        action="employee.read",
        scope_type="employee",
        scope_id=str(employee.pk),
        resource=employee,
    )
    if read_d.allowed:
        return read_d, True
    meta_d = resolve_access(
        user=request_user,
        action="employee.view_metadata",
        scope_type="employee",
        scope_id=str(employee.pk),
        resource=employee,
    )
    if not meta_d.allowed:
        return meta_d, False
    return meta_d, False


def _require_employee_action(user, employee, action: str, message: str):
    d = resolve_access(
        user=user,
        action=action,
        scope_type="employee",
        scope_id=str(employee.pk),
        resource=employee,
    )
    if not d.allowed:
        raise PermissionDenied(message)
    return d


def _pick_organization_for_editor(viewer, employee):
    shared = sorted(shared_org_ids(viewer, employee))
    if shared:
        return get_object_or_404(Organization, pk=int(shared[0]))
    own = (
        OrganizationMember.objects.select_related("organization")
        .filter(user=employee, is_active=True)
        .order_by("organization_id")
        .first()
    )
    if own is None:
        raise ValidationError({"detail": "Employee has no active organization membership."})
    return own.organization


class EmployeeListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="employeesList", responses={200: EmployeeListItemSerializer(many=True)})
    def get(self, request):
        qs = apply_employee_list_visibility(_employee_base_queryset().order_by("id"), request.user)
        rows: list[dict] = []
        read_count = 0
        metadata_count = 0
        for employee in qs:
            d, can_read = _require_employee_metadata_or_read(request.user, employee)
            if not d.allowed:
                continue
            if can_read:
                read_count += 1
            else:
                metadata_count += 1
            rows.append(
                {
                    "id": employee.id,
                    "username": employee.username or "",
                    "full_name": (employee.get_full_name() or "").strip() or (employee.username or ""),
                    "email": (employee.email or "") if can_read else "",
                    "job_title": _job_title_for(request.user, employee) if can_read else "",
                    "access_level": d.access_level,
                }
            )
        emit_audit_event(
            request,
            event_type="employee.listed",
            entity_type="employee",
            action="read",
            entity_id="",
            project_id="",
            payload={
                "count": len(rows),
                "read_count": read_count,
                "metadata_count": metadata_count,
            },
        )
        return Response(rows)


class EmployeeDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="employeesDetail", responses={200: EmployeeDetailSerializer})
    def get(self, request, user_id: int):
        employee = get_object_or_404(apply_employee_list_visibility(_employee_base_queryset(), request.user), pk=user_id)
        d, can_read = _require_employee_metadata_or_read(request.user, employee)
        if not d.allowed:
            return Response({"detail": "Forbidden."}, status=403)
        payload = _employee_detail_payload(
            employee,
            access_level=d.access_level,
            read_allowed=can_read,
            viewer=request.user,
        )
        emit_audit_event(
            request,
            event_type=("employee.content_accessed" if can_read else "employee.metadata_accessed"),
            entity_type="employee",
            action=("read" if can_read else "view_metadata"),
            entity_id=str(employee.pk),
            project_id="",
            payload=policy_audit_payload(d),
        )
        return Response(payload)

    @extend_schema(operation_id="employeesDetailPatch", request=EmployeePatchSerializer, responses={200: EmployeeDetailSerializer})
    def patch(self, request, user_id: int):
        employee = get_object_or_404(apply_employee_list_visibility(_employee_base_queryset(), request.user), pk=user_id)
        d = _require_employee_action(
            request.user,
            employee,
            "employee.update",
            "You do not have permission to update this employee profile.",
        )
        body = EmployeePatchSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        changed_fields: list[str] = []

        for field in ("first_name", "last_name", "email"):
            if field in data:
                setattr(employee, field, data[field])
                changed_fields.append(field)
        if changed_fields:
            employee.save(update_fields=changed_fields)

        title_changed = False
        if "job_title" in data:
            organization = _pick_organization_for_editor(request.user, employee)
            ctx = CareerContext(actor=request.user, reason=str(data.get("reason") or ""), request=request)
            ev = change_job_title(
                employee=employee,
                organization=organization,
                new_job_title=str(data.get("job_title") or ""),
                ctx=ctx,
            )
            if ev is not None:
                title_changed = True
                changed_fields.append("job_title")

        if not changed_fields and not title_changed:
            raise ValidationError({"detail": "No changes provided."})

        decision, can_read = _require_employee_metadata_or_read(request.user, employee)
        payload = _employee_detail_payload(
            employee,
            access_level=decision.access_level,
            read_allowed=can_read,
            viewer=request.user,
        )
        emit_audit_event(
            request,
            event_type="employee.updated",
            entity_type="employee",
            action="update",
            entity_id=str(employee.pk),
            project_id="",
            payload={
                "fields": sorted(set(changed_fields)),
                **policy_audit_payload(d),
            },
        )
        return Response(payload, status=status.HTTP_200_OK)


class EmployeeDepartmentsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="employeesDepartments", responses={200: EmployeeDepartmentSerializer(many=True)})
    def get(self, request, user_id: int):
        employee = get_object_or_404(apply_employee_list_visibility(_employee_base_queryset(), request.user), pk=user_id)
        d = resolve_access(
            user=request.user,
            action="employee.read",
            scope_type="employee",
            scope_id=str(employee.pk),
            resource=employee,
        )
        if not d.allowed:
            return Response({"detail": "You do not have permission to read employee departments."}, status=403)
        rows = [
            {
                "department_id": m.org_unit_id,
                "department_name": m.org_unit.name,
                "position": m.position or "",
                "is_lead": bool(m.is_lead),
                "joined_at": m.joined_at,
            }
            for m in OrgUnitMember.objects.select_related("org_unit")
            .filter(user=employee)
            .order_by("-is_lead", "org_unit_id")
        ]
        emit_audit_event(
            request,
            event_type="employee.departments_listed",
            entity_type="employee",
            action="read",
            entity_id=str(employee.pk),
            project_id="",
            payload={"count": len(rows), **policy_audit_payload(d)},
        )
        return Response(rows)


class EmployeeProjectsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="employeesProjects", responses={200: EmployeeProjectSerializer(many=True)})
    def get(self, request, user_id: int):
        employee = get_object_or_404(apply_employee_list_visibility(_employee_base_queryset(), request.user), pk=user_id)
        d = resolve_access(
            user=request.user,
            action="employee.read",
            scope_type="employee",
            scope_id=str(employee.pk),
            resource=employee,
        )
        if not d.allowed:
            return Response({"detail": "You do not have permission to read employee projects."}, status=403)
        rows = [
            {
                "project_id": m.project_id,
                "project_name": m.project.name,
                "project_role": m.role,
                "title_in_project": m.title_in_project or "",
                "is_active": bool(m.is_active),
                "joined_at": m.joined_at,
            }
            for m in ProjectMember.objects.select_related("project")
            .filter(user=employee)
            .order_by("-joined_at")
        ]
        emit_audit_event(
            request,
            event_type="employee.projects_listed",
            entity_type="employee",
            action="read",
            entity_id=str(employee.pk),
            project_id="",
            payload={"count": len(rows), **policy_audit_payload(d)},
        )
        return Response(rows)


class EmployeeWorkspaceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="employeesWorkspace",
        responses={200: EmployeeWorkspaceSerializer, 403: OpenApiResponse(description="Forbidden")},
    )
    def get(self, request, user_id: int):
        employee = get_object_or_404(apply_employee_list_visibility(_employee_base_queryset(), request.user), pk=user_id)
        content_d = resolve_access(
            user=request.user,
            action="employee.view_workspace_content",
            scope_type="employee",
            scope_id=str(employee.pk),
            resource=employee,
        )
        metadata_d = resolve_access(
            user=request.user,
            action="employee.view_workspace_metadata",
            scope_type="employee",
            scope_id=str(employee.pk),
            resource=employee,
        )
        if not content_d.allowed and not metadata_d.allowed:
            return Response({"detail": "You do not have access to this employee workspace."}, status=403)
        d = content_d if content_d.allowed else metadata_d
        workspace = {
            "kind": "employee",
            "employee_id": employee.pk,
            "title": (employee.get_full_name() or "").strip() or (employee.username or ""),
            "links": {
                "profile": f"/api/v1/employees/{employee.pk}",
                "departments": f"/api/v1/employees/{employee.pk}/departments",
                "projects": f"/api/v1/employees/{employee.pk}/projects",
            },
        }
        if content_d.allowed:
            workspace["links"]["personal_workspace"] = "/api/v1/workspace"
        emit_audit_event(
            request,
            event_type=(
                "employee.workspace_content_accessed"
                if content_d.allowed
                else "employee.workspace_metadata_accessed"
            ),
            entity_type="employee_workspace",
            action=("read" if content_d.allowed else "view_metadata"),
            entity_id=str(employee.pk),
            project_id="",
            payload=policy_audit_payload(d),
        )
        return Response(
            {
                "employee_id": employee.pk,
                "access_level": d.access_level,
                "policy": policy_audit_payload(d),
                "workspace": workspace,
            }
        )


class EmployeeRolesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="employeesRolesGet", responses={200: EmployeeRoleSerializer})
    def get(self, request, user_id: int):
        employee = get_object_or_404(apply_employee_list_visibility(_employee_base_queryset(), request.user), pk=user_id)
        _require_employee_action(
            request.user,
            employee,
            "employee.read",
            "You do not have permission to read employee roles.",
        )
        assignment = UserRole.objects.select_related("role").filter(user=employee).first()
        role_code = assignment.role.code if (assignment and assignment.role) else ""
        assigned_at = assignment.assigned_at if assignment else None
        return Response({"system_role": role_code, "assigned_at": assigned_at})

    @extend_schema(operation_id="employeesRolesPut", request=EmployeeRoleUpdateSerializer, responses={200: EmployeeRoleSerializer})
    def put(self, request, user_id: int):
        employee = get_object_or_404(apply_employee_list_visibility(_employee_base_queryset(), request.user), pk=user_id)
        d = _require_employee_action(
            request.user,
            employee,
            "employee.manage_roles",
            "You do not have permission to manage employee roles.",
        )
        body = EmployeeRoleUpdateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        system_role = str(body.validated_data["system_role"]).strip()
        if not Role.objects.filter(code=system_role).exists():
            raise ValidationError({"system_role": "Unknown system role."})
        actor_roles = normalized_roles_for_user(request.user)
        if system_role == "super_admin" and "super_admin" not in actor_roles:
            raise PermissionDenied("Only super admin can assign system_role=super_admin.")

        organization = _pick_organization_for_editor(request.user, employee)
        before = UserRole.objects.select_related("role").filter(user=employee).first()
        old_code = before.role.code if (before and before.role) else ""
        ctx = CareerContext(actor=request.user, reason=str(body.validated_data.get("reason") or ""), request=request)
        change_system_role(
            employee=employee,
            organization=organization,
            new_role_code=system_role,
            ctx=ctx,
        )
        after = UserRole.objects.select_related("role").filter(user=employee).first()
        new_code = after.role.code if (after and after.role) else ""
        emit_audit_event(
            request,
            event_type="employee.role_updated",
            entity_type="employee",
            action="update",
            entity_id=str(employee.pk),
            project_id="",
            payload={
                "old_role": old_code,
                "new_role": new_code,
                **policy_audit_payload(d),
            },
        )
        return Response({"system_role": new_code, "assigned_at": after.assigned_at if after else None})


class EmployeePermissionsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="employeesPermissionsList", responses={200: EmployeePermissionGrantSerializer(many=True)})
    def get(self, request, user_id: int):
        employee = get_object_or_404(apply_employee_list_visibility(_employee_base_queryset(), request.user), pk=user_id)
        _require_employee_action(
            request.user,
            employee,
            "employee.read",
            "You do not have permission to read employee permissions.",
        )
        rows = PermissionGrant.objects.filter(employee=employee).order_by("-granted_at")
        data = [
            {
                "id": g.id,
                "permission_code": g.permission_code,
                "scope_type": g.scope_type,
                "scope_id": g.scope_id or "",
                "grant_mode": g.grant_mode,
                "status": g.status,
                "expires_at": g.expires_at,
            }
            for g in rows
        ]
        return Response(data)

    @extend_schema(
        operation_id="employeesPermissionsCreate",
        request=EmployeePermissionGrantCreateSerializer,
        responses={201: EmployeePermissionGrantSerializer},
    )
    def post(self, request, user_id: int):
        employee = get_object_or_404(apply_employee_list_visibility(_employee_base_queryset(), request.user), pk=user_id)
        d = _require_employee_action(
            request.user,
            employee,
            "employee.manage_roles",
            "You do not have permission to grant employee permissions.",
        )
        body = EmployeePermissionGrantCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        scope_type = str(data.get("scope_type") or "employee").strip()
        scope_id = str(data.get("scope_id") or "").strip()
        if scope_type == "employee":
            scope_id = scope_id or str(employee.pk)
            if scope_id != str(employee.pk):
                raise ValidationError({"scope_id": "For employee scope, scope_id must equal target employee id."})
        try:
            result = access_service.grant_permission(
                employee=employee,
                permission_code=str(data["permission_code"]).strip(),
                scope_type=scope_type,
                scope_id=scope_id,
                grant_mode=str(data.get("grant_mode") or "use_only"),
                granted_by=request.user,
                expires_at=data.get("expires_at"),
                note=str(data.get("note") or ""),
                source_type=PermissionGrant.SOURCE_MANUAL,
                request=request,
            )
        except Exception as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        g = result.grant
        emit_audit_event(
            request,
            event_type="employee.permission_granted",
            entity_type="permission_grant",
            action="create",
            entity_id=str(g.pk),
            project_id="",
            payload={
                "employee_id": str(employee.pk),
                "permission_code": g.permission_code,
                "scope_type": g.scope_type,
                "scope_id": g.scope_id,
                "grant_mode": g.grant_mode,
                **policy_audit_payload(d),
            },
        )
        return Response(
            {
                "id": g.id,
                "permission_code": g.permission_code,
                "scope_type": g.scope_type,
                "scope_id": g.scope_id or "",
                "grant_mode": g.grant_mode,
                "status": g.status,
                "expires_at": g.expires_at,
            },
            status=status.HTTP_201_CREATED,
        )


class EmployeePermissionRevokeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="employeesPermissionsRevoke",
        request=EmployeePermissionGrantRevokeSerializer,
        responses={200: EmployeePermissionGrantSerializer},
    )
    def post(self, request, user_id: int, grant_id: int):
        employee = get_object_or_404(apply_employee_list_visibility(_employee_base_queryset(), request.user), pk=user_id)
        d = _require_employee_action(
            request.user,
            employee,
            "employee.manage_roles",
            "You do not have permission to revoke employee permissions.",
        )
        grant = get_object_or_404(PermissionGrant, pk=grant_id, employee=employee)
        body = EmployeePermissionGrantRevokeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        note = str(body.validated_data.get("note") or "")
        access_service.revoke_permission(
            grant,
            revoked_by=request.user,
            note=note or "employee_permissions_revoke",
            request=request,
        )
        grant.refresh_from_db()
        emit_audit_event(
            request,
            event_type="employee.permission_revoked",
            entity_type="permission_grant",
            action="revoke",
            entity_id=str(grant.pk),
            project_id="",
            payload={
                "employee_id": str(employee.pk),
                "permission_code": grant.permission_code,
                "scope_type": grant.scope_type,
                "scope_id": grant.scope_id,
                **policy_audit_payload(d),
            },
        )
        return Response(
            {
                "id": grant.id,
                "permission_code": grant.permission_code,
                "scope_type": grant.scope_type,
                "scope_id": grant.scope_id or "",
                "grant_mode": grant.grant_mode,
                "status": grant.status,
                "expires_at": grant.expires_at,
            }
        )
