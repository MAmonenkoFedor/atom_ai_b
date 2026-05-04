"""Department workspace API (OrgUnit scope, ``resolve_access`` / ``PolicyDecision``)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access.policies import policy_audit_payload, resolve_access
from apps.audit.service import emit_audit_event
from apps.orgstructure.department_permissions import (
    apply_department_list_visibility,
    compute_department_policy_decision,
    require_department_access,
    require_view_department,
)
from apps.orgstructure import department_documents as department_documents_service
from apps.organizations.models import OrganizationMember
from apps.orgstructure.api.company_admin_departments import _revoke_dept_lead_scoped_grants
from apps.orgstructure.career_service import CareerContext, assign_to_department, remove_from_department
from apps.orgstructure.models import OrgUnit, OrgUnitMember
from apps.projects.api.serializers import ProjectDocumentLinkCreateSerializer
from apps.projects.list_annotations import annotate_for_project_list, base_project_queryset
from apps.projects.project_permissions import apply_project_list_visibility
from apps.workspaces.api.serializers import DocumentSerializer

from .department_serializers import (
    DepartmentDetailSerializer,
    DepartmentEmployeeCreateSerializer,
    DepartmentEmployeeSerializer,
    DepartmentListSerializer,
    DepartmentPatchSerializer,
    DepartmentProjectStubSerializer,
)

User = get_user_model()


def _department_base_queryset():
    return OrgUnit.objects.select_related("organization", "parent").filter(is_active=True)


class DepartmentListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="departmentsList",
        responses={200: DepartmentListSerializer(many=True)},
    )
    def get(self, request):
        qs = apply_department_list_visibility(_department_base_queryset().order_by("id"), request.user)
        decisions = {ou.pk: compute_department_policy_decision(request.user, ou) for ou in qs}
        visible_pks = [pk for pk, d in decisions.items() if d.allowed]
        filtered = qs.filter(pk__in=visible_pks)
        ser = DepartmentListSerializer(
            filtered,
            many=True,
            context={"request": request, "department_decisions": decisions},
        )
        return Response(ser.data)


@extend_schema_view(
    get=extend_schema(operation_id="departmentsDetail", responses={200: DepartmentDetailSerializer}),
    patch=extend_schema(
        operation_id="departmentsDetailPatch",
        request=DepartmentPatchSerializer,
        responses={200: DepartmentDetailSerializer},
    ),
)
class DepartmentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        ou = get_object_or_404(
            apply_department_list_visibility(_department_base_queryset(), request.user),
            pk=int(pk),
        )
        decision = require_view_department(request.user, ou)
        ser = DepartmentDetailSerializer(ou, context={"request": request, "department_decision": decision})
        return Response(ser.data)

    def patch(self, request, pk: int):
        ou = get_object_or_404(
            apply_department_list_visibility(_department_base_queryset(), request.user),
            pk=int(pk),
        )
        d = require_department_access(
            request.user,
            ou,
            "department.update",
            "You do not have permission to update this department.",
        )
        ser = DepartmentPatchSerializer(ou, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        ou.refresh_from_db()
        emit_audit_event(
            request,
            event_type="department.updated",
            entity_type="department",
            action="update",
            entity_id=str(ou.pk),
            project_id="",
            payload={
                "department_id": str(ou.pk),
                "fields": sorted(ser.validated_data.keys()),
                **policy_audit_payload(d),
            },
        )
        decision = compute_department_policy_decision(request.user, ou)
        out = DepartmentDetailSerializer(
            ou,
            context={"request": request, "department_decision": decision},
        )
        return Response(out.data)


class DepartmentWorkspaceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="departmentsWorkspace",
        responses={200: OpenApiResponse(description="Department workspace descriptor")},
    )
    def get(self, request, pk: int):
        ou = get_object_or_404(
            apply_department_list_visibility(_department_base_queryset(), request.user),
            pk=int(pk),
        )
        decision = require_view_department(request.user, ou)
        read_decision = resolve_access(
            user=request.user,
            action="department.read",
            scope_type="department",
            scope_id=str(ou.pk),
            resource=ou,
        )
        workspace = None
        if read_decision.allowed:
            workspace = {
                "kind": "department",
                "department_id": ou.pk,
                "title": ou.name,
                "links": {
                    "employees": f"/api/v1/departments/{ou.pk}/employees",
                    "projects": f"/api/v1/departments/{ou.pk}/projects",
                    "documents": f"/api/v1/departments/{ou.pk}/documents",
                },
            }
        return Response(
            {
                "department_id": ou.pk,
                "access_level": decision.access_level,
                "policy": policy_audit_payload(decision),
                "workspace": workspace,
            }
        )


@extend_schema_view(
    get=extend_schema(
        operation_id="departmentsEmployeesList",
        responses={200: DepartmentEmployeeSerializer(many=True)},
    ),
    post=extend_schema(
        operation_id="departmentsEmployeesCreate",
        request=DepartmentEmployeeCreateSerializer,
        responses={201: DepartmentEmployeeSerializer},
    ),
)
class DepartmentEmployeesListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        ou = get_object_or_404(
            apply_department_list_visibility(_department_base_queryset(), request.user),
            pk=int(pk),
        )
        d = require_department_access(
            request.user,
            ou,
            "department.read",
            "You do not have permission to list employees in this department.",
        )
        emit_audit_event(
            request,
            event_type="department.employees_listed",
            entity_type="department",
            action="read",
            entity_id=str(ou.pk),
            project_id="",
            payload={**policy_audit_payload(d), "department_id": str(ou.pk)},
        )
        qs = OrgUnitMember.objects.select_related("user").filter(org_unit=ou).order_by("-is_lead", "user_id")
        ser = DepartmentEmployeeSerializer(qs, many=True, context={"request": request})
        return Response(ser.data)

    def post(self, request, pk: int):
        ou = get_object_or_404(
            apply_department_list_visibility(_department_base_queryset(), request.user),
            pk=int(pk),
        )
        d = require_department_access(
            request.user,
            ou,
            "department.manage_members",
            "You do not have permission to add employees to this department.",
        )
        body = DepartmentEmployeeCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        employee = get_object_or_404(User, pk=int(body.validated_data["user_id"]))
        if not OrganizationMember.objects.filter(
            user=employee, organization=ou.organization, is_active=True
        ).exists():
            raise ValidationError({"user_id": "User is not an active member of this organization."})
        position = (body.validated_data.get("position") or "") or ""
        is_lead = bool(body.validated_data.get("is_lead", False))
        with transaction.atomic():
            if is_lead:
                old_lead_uid = (
                    OrgUnitMember.objects.filter(org_unit=ou, is_lead=True)
                    .values_list("user_id", flat=True)
                    .first()
                )
                if old_lead_uid and int(old_lead_uid) != int(employee.pk):
                    old_user = User.objects.get(pk=int(old_lead_uid))
                    _revoke_dept_lead_scoped_grants(
                        employee=old_user,
                        org_unit_id=ou.id,
                        revoked_by=request.user,
                        request=request,
                    )
                OrgUnitMember.objects.filter(org_unit=ou, is_lead=True).exclude(user_id=employee.pk).update(
                    is_lead=False
                )
            ctx = CareerContext(actor=request.user, request=request)
            assign_to_department(
                employee=employee,
                org_unit=ou,
                position=position,
                is_lead=is_lead,
                ctx=ctx,
            )
        member = OrgUnitMember.objects.select_related("user").get(org_unit=ou, user=employee)
        emit_audit_event(
            request,
            event_type="department.employee_added",
            entity_type="department_member",
            action="create",
            entity_id=str(member.pk),
            project_id="",
            payload={
                "department_id": str(ou.pk),
                "employee_id": str(employee.pk),
                "is_lead": is_lead,
                **policy_audit_payload(d),
            },
        )
        ser = DepartmentEmployeeSerializer(member, context={"request": request})
        return Response(ser.data, status=status.HTTP_201_CREATED)


class DepartmentEmployeeDetailView(APIView):
    """Remove a member by **employee** user id (same id as ``user_id`` in list payload)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="departmentsEmployeesDestroy",
        request=None,
        responses={204: OpenApiResponse(description="Employee removed from department")},
    )
    def delete(self, request, pk: int, employee_id: int):
        ou = get_object_or_404(
            apply_department_list_visibility(_department_base_queryset(), request.user),
            pk=int(pk),
        )
        d = require_department_access(
            request.user,
            ou,
            "department.manage_members",
            "You do not have permission to remove employees from this department.",
        )
        member = get_object_or_404(
            OrgUnitMember.objects.select_related("user"),
            org_unit=ou,
            user_id=int(employee_id),
        )
        employee = member.user
        if member.is_lead:
            _revoke_dept_lead_scoped_grants(
                employee=employee,
                org_unit_id=ou.id,
                revoked_by=request.user,
                request=request,
            )
        ctx = CareerContext(actor=request.user, request=request)
        remove_from_department(employee=employee, org_unit=ou, ctx=ctx)
        emit_audit_event(
            request,
            event_type="department.employee_removed",
            entity_type="department_member",
            action="delete",
            entity_id=str(member.pk),
            project_id="",
            payload={
                "department_id": str(ou.pk),
                "employee_id": str(employee_id),
                **policy_audit_payload(d),
            },
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DepartmentProjectsListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="departmentsProjectsList",
        responses={200: DepartmentProjectStubSerializer(many=True)},
    )
    def get(self, request, pk: int):
        ou = get_object_or_404(
            apply_department_list_visibility(_department_base_queryset(), request.user),
            pk=int(pk),
        )
        d = require_department_access(
            request.user,
            ou,
            "department.read",
            "You do not have permission to list projects for this department.",
        )
        emit_audit_event(
            request,
            event_type="department.projects_listed",
            entity_type="department",
            action="read",
            entity_id=str(ou.pk),
            project_id="",
            payload={**policy_audit_payload(d), "department_id": str(ou.pk)},
        )
        qs = apply_project_list_visibility(
            base_project_queryset().filter(primary_org_unit=ou),
            request.user,
        )
        qs = annotate_for_project_list(qs, request.user).order_by("-created_at")
        ser = DepartmentProjectStubSerializer(qs, many=True, context={"request": request})
        return Response(ser.data)


class DepartmentDocumentsListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="departmentsDocumentsList", responses=DocumentSerializer(many=True))
    def get(self, request, pk: int):
        ou = get_object_or_404(
            apply_department_list_visibility(_department_base_queryset(), request.user),
            pk=int(pk),
        )
        require_view_department(request.user, ou)
        docs = department_documents_service.list_department_documents(request, ou)
        has_content_links = any(bool((row.get("href") or "").strip()) for row in docs)
        emit_audit_event(
            request,
            event_type=(
                "department.document_content_accessed"
                if has_content_links
                else "department.document_metadata_accessed"
            ),
            entity_type="department_document",
            action=("read" if has_content_links else "view_metadata"),
            entity_id="",
            project_id="",
            payload={"count": len(docs)},
        )
        return Response(docs)


class DepartmentDocumentUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(operation_id="departmentsDocumentUpload", responses=DocumentSerializer)
    def post(self, request, pk: int):
        ou = get_object_or_404(
            apply_department_list_visibility(_department_base_queryset(), request.user),
            pk=int(pk),
        )
        require_view_department(request.user, ou)
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": "No file uploaded."})
        doc = department_documents_service.create_department_document_upload(request, ou, upload)
        emit_audit_event(
            request,
            event_type="department.document_uploaded",
            entity_type="department_document",
            action="create",
            entity_id=str(doc.get("id") or ""),
            project_id="",
            payload={"title": doc.get("title"), "type": doc.get("type")},
        )
        return Response(doc, status=status.HTTP_201_CREATED)


class DepartmentDocumentLinkView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="departmentsDocumentLinkCreate",
        request=ProjectDocumentLinkCreateSerializer,
        responses=DocumentSerializer,
    )
    def post(self, request, pk: int):
        ou = get_object_or_404(
            apply_department_list_visibility(_department_base_queryset(), request.user),
            pk=int(pk),
        )
        require_view_department(request.user, ou)
        serializer = ProjectDocumentLinkCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doc = department_documents_service.create_department_document_link(
            request,
            ou,
            serializer.validated_data["title"],
            str(serializer.validated_data["url"]),
        )
        emit_audit_event(
            request,
            event_type="department.document_linked",
            entity_type="department_document",
            action="create",
            entity_id=str(doc.get("id") or ""),
            project_id="",
            payload={"title": doc.get("title"), "type": "link"},
        )
        return Response(doc, status=status.HTTP_201_CREATED)
