"""REST API for the access-control service.

Endpoints (all under ``/api/v1/access/``):

* ``GET/POST /permissions`` — permissions catalog (super-admin only to mutate)
* ``PATCH /permissions/<id>`` — toggle / rename
* ``GET/POST /role-templates`` — templates
* ``PATCH /role-templates/<id>`` — edit template
* ``GET/POST /role-templates/<id>/permissions`` — list/replace template items
* ``GET/POST /grants`` — direct grants
* ``POST /grants/<id>/revoke`` — revoke
* ``GET /employees/<id>/grants`` — grants for one employee
* ``GET /employees/<id>/effective-permissions`` — resolver output
* ``GET /employees/<id>/templates`` — role-template assignments
* ``POST /employees/<id>/templates`` — assign template
* ``DELETE /employees/<id>/templates/<assignment_id>`` — remove template
* ``GET /employees/<id>/audit`` — dedicated permission audit stream
* ``GET/PATCH /delegation-rules[/<id>]`` — delegation rules

Permissions model for v1:

* **Super admin** can call every endpoint.
* **Company admin** can read catalog + templates + grants within their org,
  and can grant/revoke any permission for users in their organization except
  for ``rights.grant`` / ``rights.revoke`` / ``roles.assign`` which remain
  super-admin-only.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access import resolver, service
from apps.access.api.serializers import (
    DenyCreateSerializer,
    DenyRevokeSerializer,
    DelegationRuleSerializer,
    GrantCreateSerializer,
    GrantRevokeSerializer,
    PermissionAuditLogSerializer,
    PermissionDefinitionSerializer,
    PermissionDenySerializer,
    PermissionGrantSerializer,
    RoleTemplateAssignmentSerializer,
    RoleTemplatePermissionSerializer,
    RoleTemplateSerializer,
    TemplateAssignSerializer,
    TemplatePermissionInputSerializer,
)
from apps.access.models import (
    DelegationRule,
    PermissionAuditLog,
    PermissionDefinition,
    PermissionDeny,
    PermissionGrant,
    RoleTemplate,
    RoleTemplateAssignment,
    RoleTemplatePermission,
)
from apps.core.api.permissions import (
    IsCompanyAdminOrSuperAdmin,
    IsSuperAdmin,
    normalized_roles_for_user,
)

User = get_user_model()


# Permissions that require super-admin even for company admins.
_SUPER_ADMIN_ONLY_CODES = frozenset({"rights.grant", "rights.revoke", "roles.assign"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_project_delegation(user, parent_grant: PermissionGrant | None, *, scope_type: str) -> bool:
    return bool(
        parent_grant
        and parent_grant.employee_id == getattr(user, "id", None)
        and parent_grant.scope_type == "project"
        and scope_type == "project"
    )


def _ensure_can_manage(user, *, permission_code: str) -> None:
    roles = normalized_roles_for_user(user)
    if "super_admin" in roles:
        return
    if permission_code in _SUPER_ADMIN_ONLY_CODES:
        raise PermissionDenied(
            "Этот тип прав может выдавать только супер-админ."
        )
    if "company_admin" not in roles:
        raise PermissionDenied("Недостаточно прав для управления правами.")


def _page(request, queryset, serializer_cls, *, default_limit: int = 100):
    try:
        limit = int(request.query_params.get("limit", default_limit))
    except (TypeError, ValueError):
        limit = default_limit
    limit = max(1, min(500, limit))
    try:
        offset = int(request.query_params.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    total = queryset.count()
    rows = list(queryset[offset : offset + limit])
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": serializer_cls(rows, many=True).data,
    }


# ---------------------------------------------------------------------------
# Permissions catalog
# ---------------------------------------------------------------------------


class PermissionsCatalogView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    def get(self, request):
        qs = PermissionDefinition.objects.all()
        module = request.query_params.get("module")
        if module:
            qs = qs.filter(module=module)
        code = request.query_params.get("code")
        if code:
            qs = qs.filter(code__icontains=code)
        only_active = request.query_params.get("active")
        if only_active is not None:
            qs = qs.filter(is_active=only_active.lower() in ("1", "true", "yes"))
        return Response(_page(request, qs.order_by("module", "code"), PermissionDefinitionSerializer))

    def post(self, request):
        roles = normalized_roles_for_user(request.user)
        if "super_admin" not in roles:
            raise PermissionDenied("Каталог прав редактирует только супер-админ.")
        serializer = PermissionDefinitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        definition = serializer.save()
        service._record_audit(  # noqa: SLF001 — internal helper, we own both sides
            request=request,
            actor=request.user,
            target=None,
            action=PermissionAuditLog.ACTION_DEFINITION_UPDATED,
            permission_code=definition.code,
            new_value=PermissionDefinitionSerializer(definition).data,
            note="definition_created",
        )
        return Response(
            PermissionDefinitionSerializer(definition).data, status=status.HTTP_201_CREATED
        )


class PermissionDefinitionDetailView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def patch(self, request, pk: int):
        definition = get_object_or_404(PermissionDefinition, pk=pk)
        before = PermissionDefinitionSerializer(definition).data
        serializer = PermissionDefinitionSerializer(definition, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        definition = serializer.save()
        service._record_audit(  # noqa: SLF001
            request=request,
            actor=request.user,
            target=None,
            action=PermissionAuditLog.ACTION_DEFINITION_UPDATED,
            permission_code=definition.code,
            old_value=before,
            new_value=PermissionDefinitionSerializer(definition).data,
            note="definition_updated",
        )
        return Response(PermissionDefinitionSerializer(definition).data)


# ---------------------------------------------------------------------------
# Role templates
# ---------------------------------------------------------------------------


class RoleTemplatesView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    def get(self, request):
        qs = RoleTemplate.objects.all().prefetch_related("permissions")
        active = request.query_params.get("active")
        if active is not None:
            qs = qs.filter(is_active=active.lower() in ("1", "true", "yes"))
        return Response(_page(request, qs.order_by("code"), RoleTemplateSerializer))

    def post(self, request):
        roles = normalized_roles_for_user(request.user)
        if "super_admin" not in roles:
            raise PermissionDenied("Шаблоны может создавать только супер-админ.")
        serializer = RoleTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        template = serializer.save()
        return Response(
            RoleTemplateSerializer(template).data, status=status.HTTP_201_CREATED
        )


class RoleTemplateDetailView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def patch(self, request, pk: int):
        template = get_object_or_404(RoleTemplate, pk=pk)
        serializer = RoleTemplateSerializer(template, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        template = serializer.save()
        return Response(RoleTemplateSerializer(template).data)


class RoleTemplatePermissionsView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request, pk: int):
        template = get_object_or_404(RoleTemplate, pk=pk)
        qs = template.permissions.all()
        return Response(RoleTemplatePermissionSerializer(qs, many=True).data)

    def post(self, request, pk: int):
        """Replace the full set of permissions attached to a template."""

        template = get_object_or_404(RoleTemplate, pk=pk)
        raw = request.data.get("permissions", request.data)
        if not isinstance(raw, list):
            raise ValidationError({"permissions": "expected a list"})
        parsed = [TemplatePermissionInputSerializer(data=item) for item in raw]
        for item in parsed:
            item.is_valid(raise_exception=True)

        desired_codes = {p.validated_data["permission_code"] for p in parsed}
        unknown_codes = desired_codes - set(
            PermissionDefinition.objects.filter(code__in=desired_codes).values_list(
                "code", flat=True
            )
        )
        if unknown_codes:
            raise ValidationError(
                {"permissions": f"Unknown codes: {', '.join(sorted(unknown_codes))}"}
            )

        for item in parsed:
            data = item.validated_data
            RoleTemplatePermission.objects.update_or_create(
                role_template=template,
                permission_code=data["permission_code"],
                defaults={
                    "grant_mode": data["grant_mode"],
                    "default_enabled": data["default_enabled"],
                },
            )
        RoleTemplatePermission.objects.filter(role_template=template).exclude(
            permission_code__in=desired_codes
        ).delete()
        return Response(
            RoleTemplatePermissionSerializer(
                template.permissions.all(), many=True
            ).data
        )


# ---------------------------------------------------------------------------
# Grants
# ---------------------------------------------------------------------------


class GrantsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _ensure_can_manage(request.user, permission_code="docs.view")
        qs = PermissionGrant.objects.select_related("employee", "granted_by", "revoked_by").all()
        employee_id = request.query_params.get("employee_id")
        if employee_id:
            qs = qs.filter(employee_id=employee_id)
        permission_code = request.query_params.get("permission_code")
        if permission_code:
            qs = qs.filter(permission_code=permission_code)
        scope_type = request.query_params.get("scope_type")
        if scope_type:
            qs = qs.filter(scope_type=scope_type)
        scope_id = request.query_params.get("scope_id")
        if scope_id is not None:
            qs = qs.filter(scope_id=scope_id)
        status_param = request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        return Response(_page(request, qs.order_by("-granted_at"), PermissionGrantSerializer))

    def post(self, request):
        payload = GrantCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        employee = get_object_or_404(User, pk=data["employee_id"])
        parent_grant = None
        if data.get("parent_grant_id"):
            parent_grant = get_object_or_404(PermissionGrant, pk=data["parent_grant_id"])

        if not _is_project_delegation(
            request.user,
            parent_grant,
            scope_type=data["scope_type"],
        ):
            _ensure_can_manage(request.user, permission_code=data["permission_code"])

        source_type = (
            PermissionGrant.SOURCE_DELEGATION
            if parent_grant
            else PermissionGrant.SOURCE_MANUAL
        )

        try:
            result = service.grant_permission(
                employee=employee,
                permission_code=data["permission_code"],
                scope_type=data["scope_type"],
                scope_id=data.get("scope_id", ""),
                grant_mode=data.get("grant_mode", PermissionGrant.GRANT_MODE_USE_ONLY),
                granted_by=request.user,
                expires_at=data.get("expires_at"),
                note=data.get("note", ""),
                source_type=source_type,
                parent_grant=parent_grant,
                request=request,
            )
        except service.AccessControlError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

        return Response(
            PermissionGrantSerializer(result.grant).data, status=status.HTTP_201_CREATED
        )


class GrantRevokeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        grant = get_object_or_404(PermissionGrant, pk=pk)
        if not (
            grant.source_type == PermissionGrant.SOURCE_DELEGATION
            and grant.granted_by_id == request.user.id
            and grant.scope_type == "project"
        ):
            _ensure_can_manage(request.user, permission_code=grant.permission_code)

        payload = GrantRevokeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        grant = service.revoke_permission(
            grant,
            revoked_by=request.user,
            note=payload.validated_data.get("note", ""),
            request=request,
        )
        return Response(PermissionGrantSerializer(grant).data)


class DeniesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _ensure_can_manage(request.user, permission_code="docs.view")
        qs = PermissionDeny.objects.select_related("employee", "denied_by", "revoked_by").all()
        employee_id = request.query_params.get("employee_id")
        if employee_id:
            qs = qs.filter(employee_id=employee_id)
        permission_code = request.query_params.get("permission_code")
        if permission_code:
            qs = qs.filter(permission_code=permission_code)
        scope_type = request.query_params.get("scope_type")
        if scope_type:
            qs = qs.filter(scope_type=scope_type)
        scope_id = request.query_params.get("scope_id")
        if scope_id is not None:
            qs = qs.filter(scope_id=scope_id)
        status_param = request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        return Response(_page(request, qs.order_by("-denied_at"), PermissionDenySerializer))

    def post(self, request):
        payload = DenyCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        employee = get_object_or_404(User, pk=data["employee_id"])
        _ensure_can_manage(request.user, permission_code=data["permission_code"])
        try:
            result = service.deny_permission(
                employee=employee,
                permission_code=data["permission_code"],
                scope_type=data["scope_type"],
                scope_id=data.get("scope_id", ""),
                denied_by=request.user,
                expires_at=data.get("expires_at"),
                note=data.get("note", ""),
                source_type=PermissionDeny.SOURCE_MANUAL,
                request=request,
            )
        except service.AccessControlError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

        return Response(
            PermissionDenySerializer(result.deny).data, status=status.HTTP_201_CREATED
        )


class DenyRevokeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        deny = get_object_or_404(PermissionDeny, pk=pk)
        _ensure_can_manage(request.user, permission_code=deny.permission_code)
        payload = DenyRevokeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        deny = service.revoke_deny(
            deny,
            revoked_by=request.user,
            note=payload.validated_data.get("note", ""),
            request=request,
        )
        return Response(PermissionDenySerializer(deny).data)


# ---------------------------------------------------------------------------
# Employee-scoped endpoints
# ---------------------------------------------------------------------------


class EmployeeGrantsView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    def get(self, request, employee_id: int):
        employee = get_object_or_404(User, pk=employee_id)
        qs = (
            PermissionGrant.objects.filter(employee=employee)
            .select_related("granted_by", "revoked_by")
            .order_by("-granted_at")
        )
        return Response(PermissionGrantSerializer(qs, many=True).data)


class EmployeeDeniesView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    def get(self, request, employee_id: int):
        employee = get_object_or_404(User, pk=employee_id)
        qs = (
            PermissionDeny.objects.filter(employee=employee)
            .select_related("denied_by", "revoked_by")
            .order_by("-denied_at")
        )
        return Response(PermissionDenySerializer(qs, many=True).data)


class EmployeeEffectivePermissionsView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    def get(self, request, employee_id: int):
        employee = get_object_or_404(User, pk=employee_id)
        effective = resolver.list_effective_permissions(employee)
        sources = resolver.list_permission_sources(employee)
        return Response({"effective": effective, "sources": sources})


class EmployeeTemplatesView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    def get(self, request, employee_id: int):
        employee = get_object_or_404(User, pk=employee_id)
        qs = (
            RoleTemplateAssignment.objects.filter(employee=employee)
            .select_related("role_template", "assigned_by")
            .order_by("-created_at")
        )
        return Response(RoleTemplateAssignmentSerializer(qs, many=True).data)

    def post(self, request, employee_id: int):
        roles = normalized_roles_for_user(request.user)
        if "super_admin" not in roles and "company_admin" not in roles:
            raise PermissionDenied("Нет прав назначать шаблоны.")

        payload = TemplateAssignSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        employee = get_object_or_404(User, pk=employee_id)
        if data["employee_id"] != employee.id:
            raise ValidationError({"employee_id": "mismatch"})
        role_template = get_object_or_404(RoleTemplate, pk=data["role_template_id"])
        try:
            result = service.assign_role_template(
                employee=employee,
                role_template=role_template,
                scope_type=data.get("scope_type") or "",
                scope_id=data.get("scope_id") or "",
                assigned_by=request.user,
                note=data.get("note") or "",
                request=request,
            )
        except service.AccessControlError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

        return Response(
            RoleTemplateAssignmentSerializer(result.assignment).data,
            status=status.HTTP_201_CREATED,
        )


class EmployeeTemplateDetailView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    def delete(self, request, employee_id: int, assignment_id: int):
        assignment = get_object_or_404(
            RoleTemplateAssignment, pk=assignment_id, employee_id=employee_id
        )
        service.remove_role_template(
            assignment,
            actor=request.user,
            note=request.data.get("note", "") if hasattr(request, "data") else "",
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmployeePermissionAuditView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    def get(self, request, employee_id: int):
        employee = get_object_or_404(User, pk=employee_id)
        qs = (
            PermissionAuditLog.objects.filter(
                Q(target_employee=employee) | Q(actor=employee)
            )
            .select_related("actor", "target_employee")
            .order_by("-created_at", "-id")
        )
        return Response(_page(request, qs, PermissionAuditLogSerializer, default_limit=50))


# ---------------------------------------------------------------------------
# Delegation rules
# ---------------------------------------------------------------------------


class DelegationRulesView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        qs = DelegationRule.objects.all()
        permission_code = request.query_params.get("permission_code")
        if permission_code:
            qs = qs.filter(permission_code=permission_code)
        return Response(DelegationRuleSerializer(qs.order_by("permission_code"), many=True).data)


class DelegationRuleDetailView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def patch(self, request, pk: int):
        rule = get_object_or_404(DelegationRule, pk=pk)
        before = DelegationRuleSerializer(rule).data
        serializer = DelegationRuleSerializer(rule, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        rule = serializer.save()
        service._record_audit(  # noqa: SLF001
            request=request,
            actor=request.user,
            target=None,
            action=PermissionAuditLog.ACTION_RULE_UPDATED,
            permission_code=rule.permission_code,
            old_value=before,
            new_value=DelegationRuleSerializer(rule).data,
            note="rule_updated",
        )
        return Response(DelegationRuleSerializer(rule).data)
