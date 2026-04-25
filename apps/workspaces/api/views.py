from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, PolymorphicProxySerializer, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.service import emit_audit_event
from apps.workspaces import data, documents_service

from .serializers import (
    BuildingDetailSerializer,
    BuildingListItemSerializer,
    DepartmentSerializer,
    DocumentSerializer,
    EmployeeProfileSerializer,
    EmployeeOwnerProfileSerializer,
    EmployeePublicProfileSerializer,
    EmployeeWorkspaceContextSerializer,
    TaskSerializer,
    WorkspaceTaskAliasCreateSerializer,
    WorkspaceTaskAliasPatchSerializer,
    QuickTaskCreateResponseSerializer,
    QuickTaskCreateSerializer,
    UpdateMyEmployeeProfileSerializer,
    WorkspaceEmployeeCabinetSerializer,
    WorkspaceSerializer,
    WorkspaceTaskChecklistCreateSerializer,
    WorkspaceTaskChecklistPatchSerializer,
    WorkspaceTaskCommentCreateSerializer,
    WorkspaceDocumentLinkCreateSerializer,
)


@method_decorator(cache_page(60), name="dispatch")
class BuildingsListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="buildingsList",
        responses=BuildingListItemSerializer(many=True),
    )
    def get(self, request):
        payload = data.list_buildings()
        return Response(BuildingListItemSerializer(payload, many=True).data)


@method_decorator(cache_page(60), name="dispatch")
class BuildingDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="buildingDetail",
        responses=BuildingDetailSerializer,
    )
    def get(self, request, building_id: str):
        payload = data.get_building_detail(building_id)
        return Response(BuildingDetailSerializer(payload).data)


@method_decorator(cache_page(60), name="dispatch")
class BuildingDepartmentsView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="buildingDepartments",
        responses=DepartmentSerializer(many=True),
    )
    def get(self, request, building_id: str):
        payload = data.get_departments(building_id)
        return Response(DepartmentSerializer(payload, many=True).data)


@method_decorator(cache_page(60), name="dispatch")
class FloorWorkspaceView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="floorWorkspace",
        responses=WorkspaceSerializer,
    )
    def get(self, request, building_id: str, floor_id: str):
        payload = data.get_floor_workspace(building_id, floor_id)
        return Response(WorkspaceSerializer(payload).data)


@method_decorator(cache_page(60), name="dispatch")
class EmployeeWorkspaceContextView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="employeeWorkspaceContext",
        responses=EmployeeWorkspaceContextSerializer,
    )
    def get(self, request, building_id: str, floor_id: str, employee_id: str):
        payload = data.get_employee_workspace_context(building_id, floor_id, employee_id)
        return Response(EmployeeWorkspaceContextSerializer(payload).data)


@method_decorator(cache_page(60), name="dispatch")
class EmployeeProfileView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="employeeProfileByFloor",
        responses=EmployeeProfileSerializer,
    )
    def get(self, request, building_id: str, floor_id: str, employee_id: str):
        payload = data.get_employee_profile(building_id, floor_id, employee_id)
        return Response(EmployeeProfileSerializer(payload).data)


@method_decorator(cache_page(60), name="dispatch")
class WorkspaceContextAliasView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="workspaceContextAlias",
        parameters=[OpenApiParameter("employee_id", OpenApiTypes.STR, required=True)],
        responses=EmployeeWorkspaceContextSerializer,
    )
    def get(self, request, building_id: str, floor_id: str):
        employee_id = request.query_params.get("employee_id")
        if not employee_id:
            raise ValidationError({"detail": "employee_id query param is required."})
        payload = data.get_employee_workspace_context(building_id, floor_id, employee_id)
        return Response(EmployeeWorkspaceContextSerializer(payload).data)


@method_decorator(cache_page(60), name="dispatch")
class WorkspaceContextGlobalAliasView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="workspaceContextGlobalAlias",
        parameters=[
            OpenApiParameter("building_id", OpenApiTypes.STR, required=True),
            OpenApiParameter("floor_id", OpenApiTypes.STR, required=True),
            OpenApiParameter("employee_id", OpenApiTypes.STR, required=True),
        ],
        responses=EmployeeWorkspaceContextSerializer,
    )
    def get(self, request):
        building_id = request.query_params.get("building_id")
        floor_id = request.query_params.get("floor_id")
        employee_id = request.query_params.get("employee_id")
        if not building_id or not floor_id or not employee_id:
            raise ValidationError(
                {"detail": "building_id, floor_id and employee_id query params are required."}
            )
        payload = data.get_employee_workspace_context(building_id, floor_id, employee_id)
        return Response(EmployeeWorkspaceContextSerializer(payload).data)


@method_decorator(cache_page(60), name="dispatch")
class EmployeeProfileGlobalAliasView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="employeeProfileGlobalAlias",
        parameters=[
            OpenApiParameter("building_id", OpenApiTypes.STR, required=True),
            OpenApiParameter("floor_id", OpenApiTypes.STR, required=True),
        ],
        responses=EmployeeProfileSerializer,
    )
    def get(self, request, employee_id: str):
        building_id = request.query_params.get("building_id")
        floor_id = request.query_params.get("floor_id")
        if not building_id or not floor_id:
            raise ValidationError({"detail": "building_id and floor_id query params are required."})
        payload = data.get_employee_profile(building_id, floor_id, employee_id)
        return Response(EmployeeProfileSerializer(payload).data)


def _resolve_viewer_role(user) -> str:
    assignment = user.role_assignments.select_related("role").first()
    if not assignment:
        return "employee"
    role_code = assignment.role.code
    if role_code == "admin":
        return "company_admin"
    if role_code in {"employee", "manager", "company_admin", "executive", "ceo", "super_admin"}:
        return role_code
    return "employee"


class EmployeeWorkspaceCabinetView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="employeeWorkspaceCabinet", responses=WorkspaceEmployeeCabinetSerializer)
    def get(self, request):
        viewer_role = _resolve_viewer_role(request.user)
        payload = data.get_employee_workspace(request, viewer_role)
        return Response(WorkspaceEmployeeCabinetSerializer(payload).data)


class WorkspaceDocumentUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(operation_id="workspaceDocumentUpload", responses=DocumentSerializer)
    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": "No file uploaded."})
        doc = documents_service.create_workspace_document_upload(request, upload)
        return Response(DocumentSerializer(doc).data, status=201)


class WorkspaceDocumentLinkView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="workspaceDocumentLinkCreate",
        request=WorkspaceDocumentLinkCreateSerializer,
        responses=DocumentSerializer,
    )
    def post(self, request):
        serializer = WorkspaceDocumentLinkCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doc = documents_service.create_workspace_document_link(
            request,
            serializer.validated_data["title"],
            str(serializer.validated_data["url"]),
        )
        return Response(DocumentSerializer(doc).data, status=201)


class EmployeeMeProfileView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="employeeMeProfile", responses=EmployeeOwnerProfileSerializer)
    def get(self, request):
        employee_id = data.resolve_employee_id_for_username(request.user.username)
        payload = data.get_employee_owner_profile(employee_id)
        return Response(EmployeeOwnerProfileSerializer(payload).data)

    @extend_schema(
        operation_id="employeeMeProfilePatch",
        request=UpdateMyEmployeeProfileSerializer,
        responses=EmployeeOwnerProfileSerializer,
    )
    def patch(self, request):
        serializer = UpdateMyEmployeeProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee_id = data.resolve_employee_id_for_username(request.user.username)
        payload = data.patch_employee_owner_profile(employee_id, serializer.validated_data)
        return Response(EmployeeOwnerProfileSerializer(payload).data)


class EmployeeProfileByIdView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="employeeProfileOwnerOrPublic",
        responses={
            200: PolymorphicProxySerializer(
                component_name="EmployeeProfileOwnerOrPublicResponse",
                serializers=[EmployeeOwnerProfileSerializer, EmployeePublicProfileSerializer],
                resource_type_field_name="view",
            )
        },
    )
    def get(self, request, employee_id: str):
        own_employee_id = data.resolve_employee_id_for_username(request.user.username)
        if employee_id == own_employee_id:
            payload = data.get_employee_owner_profile(employee_id)
            return Response(EmployeeOwnerProfileSerializer(payload).data)
        payload = data.get_employee_public_profile(employee_id)
        return Response(EmployeePublicProfileSerializer(payload).data)


class WorkspaceQuickTasksView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="workspaceQuickTasksCreate",
        request=QuickTaskCreateSerializer,
        responses=QuickTaskCreateResponseSerializer,
    )
    def post(self, request):
        serializer = QuickTaskCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee_id = data.resolve_employee_id_for_username(request.user.username)
        payload = data.create_workspace_quick_task(
            employee_id=employee_id,
            title=serializer.validated_data["title"],
            slot=serializer.validated_data["slot"],
            priority=serializer.validated_data.get("priority"),
            project_id=serializer.validated_data.get("project_id"),
        )
        actor_name, actor_role = _workspace_actor(request)
        data.append_workspace_task_audit(
            employee_id,
            payload["task_id"],
            "created",
            actor_name,
            actor_role,
            "Quick task",
        )
        emit_audit_event(
            request,
            event_type="workspace.quick_task_created",
            entity_type="workspace_task",
            action="create",
            entity_id=str(payload["task_id"]),
            project_id=str(payload.get("project_id") or ""),
            task_id=str(payload["task_id"]),
            payload={"title": payload.get("title", ""), "slot": payload.get("slot", "")},
        )
        return Response(QuickTaskCreateResponseSerializer(payload).data, status=201)


def _require_workspace_scope_query(request):
    building_id = request.query_params.get("building_id")
    floor_id = request.query_params.get("floor_id")
    if not building_id or not floor_id:
        raise ValidationError({"detail": "building_id and floor_id query params are required."})
    return str(building_id), str(floor_id)


def _workspace_actor(request) -> tuple[str, str]:
    user = request.user
    name = (user.get_full_name() or "").strip() or user.username
    un = (user.username or "").lower()
    role = "employee"
    if un.startswith("manager"):
        role = "manager"
    elif "admin" in un:
        role = "company_admin"
    return name, role


class WorkspaceTasksAliasView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="workspaceTasksAliasList",
        parameters=[
            OpenApiParameter("building_id", OpenApiTypes.STR, required=True),
            OpenApiParameter("floor_id", OpenApiTypes.STR, required=True),
            OpenApiParameter("q", OpenApiTypes.STR),
            OpenApiParameter("column", OpenApiTypes.STR),
            OpenApiParameter("status", OpenApiTypes.STR),
            OpenApiParameter("priority", OpenApiTypes.STR),
        ],
        responses=TaskSerializer(many=True),
    )
    def get(self, request):
        _require_workspace_scope_query(request)
        employee_id = data.resolve_employee_id_for_username(request.user.username)
        payload = data.list_workspace_tasks(
            employee_id,
            {
                "q": request.query_params.get("q"),
                "column": request.query_params.get("column"),
                "status": request.query_params.get("status"),
                "priority": request.query_params.get("priority"),
            },
        )
        return Response(TaskSerializer(payload, many=True).data)

    @extend_schema(
        operation_id="workspaceTasksAliasCreate",
        parameters=[
            OpenApiParameter("building_id", OpenApiTypes.STR, required=True),
            OpenApiParameter("floor_id", OpenApiTypes.STR, required=True),
        ],
        request=WorkspaceTaskAliasCreateSerializer,
        responses=TaskSerializer,
    )
    def post(self, request):
        _require_workspace_scope_query(request)
        serializer = WorkspaceTaskAliasCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee_id = data.resolve_employee_id_for_username(request.user.username)
        payload = data.create_workspace_task(employee_id, serializer.validated_data)
        actor_name, actor_role = _workspace_actor(request)
        data.append_workspace_task_audit(
            employee_id,
            payload["id"],
            "created",
            actor_name,
            actor_role,
            "Task created",
        )
        emit_audit_event(
            request,
            event_type="workspace.task_created",
            entity_type="workspace_task",
            action="create",
            entity_id=str(payload["id"]),
            project_id=str(payload.get("project_id") or ""),
            task_id=str(payload["id"]),
            payload={"title": payload.get("title", ""), "column": payload.get("column", "")},
        )
        return Response(TaskSerializer(payload).data, status=201)


class WorkspaceTaskAuditView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="workspaceTaskAuditList",
        parameters=[
            OpenApiParameter("building_id", OpenApiTypes.STR, required=True),
            OpenApiParameter("floor_id", OpenApiTypes.STR, required=True),
        ],
    )
    def get(self, request, task_id: str):
        _require_workspace_scope_query(request)
        employee_id = data.resolve_employee_id_for_username(request.user.username)
        payload = data.list_workspace_task_audit_events(employee_id, task_id)
        return Response(payload)


class WorkspaceTaskCommentsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="workspaceTaskCommentsList",
        parameters=[
            OpenApiParameter("building_id", OpenApiTypes.STR, required=True),
            OpenApiParameter("floor_id", OpenApiTypes.STR, required=True),
        ],
    )
    def get(self, request, task_id: str):
        _require_workspace_scope_query(request)
        employee_id = data.resolve_employee_id_for_username(request.user.username)
        payload = data.list_workspace_task_comments(employee_id, task_id)
        return Response(payload)

    @extend_schema(
        operation_id="workspaceTaskCommentsCreate",
        parameters=[
            OpenApiParameter("building_id", OpenApiTypes.STR, required=True),
            OpenApiParameter("floor_id", OpenApiTypes.STR, required=True),
        ],
        request=WorkspaceTaskCommentCreateSerializer,
    )
    def post(self, request, task_id: str):
        _require_workspace_scope_query(request)
        serializer = WorkspaceTaskCommentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee_id = data.resolve_employee_id_for_username(request.user.username)
        actor_name, actor_role = _workspace_actor(request)
        data.add_workspace_task_comment(
            employee_id,
            task_id,
            serializer.validated_data["message"],
            actor_name,
            actor_role,
        )
        data.append_workspace_task_audit(
            employee_id,
            task_id,
            "commented",
            actor_name,
            actor_role,
            "Comment added",
        )
        emit_audit_event(
            request,
            event_type="workspace.task_commented",
            entity_type="workspace_task_comment",
            action="create",
            entity_id="",
            task_id=str(task_id),
            payload={"message_len": len(serializer.validated_data["message"])},
        )
        return Response(status=204)


class WorkspaceTaskChecklistView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="workspaceTaskChecklistList",
        parameters=[
            OpenApiParameter("building_id", OpenApiTypes.STR, required=True),
            OpenApiParameter("floor_id", OpenApiTypes.STR, required=True),
        ],
    )
    def get(self, request, task_id: str):
        _require_workspace_scope_query(request)
        employee_id = data.resolve_employee_id_for_username(request.user.username)
        payload = data.list_workspace_task_checklist(employee_id, task_id)
        return Response(payload)

    @extend_schema(
        operation_id="workspaceTaskChecklistCreate",
        parameters=[
            OpenApiParameter("building_id", OpenApiTypes.STR, required=True),
            OpenApiParameter("floor_id", OpenApiTypes.STR, required=True),
        ],
        request=WorkspaceTaskChecklistCreateSerializer,
    )
    def post(self, request, task_id: str):
        _require_workspace_scope_query(request)
        serializer = WorkspaceTaskChecklistCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee_id = data.resolve_employee_id_for_username(request.user.username)
        actor_name, actor_role = _workspace_actor(request)
        data.add_workspace_task_checklist_item(employee_id, task_id, serializer.validated_data["title"])
        data.append_workspace_task_audit(
            employee_id,
            task_id,
            "updated",
            actor_name,
            actor_role,
            "Checklist item added",
        )
        return Response(status=204)


class WorkspaceTaskChecklistItemView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="workspaceTaskChecklistPatch",
        parameters=[
            OpenApiParameter("building_id", OpenApiTypes.STR, required=True),
            OpenApiParameter("floor_id", OpenApiTypes.STR, required=True),
        ],
        request=WorkspaceTaskChecklistPatchSerializer,
    )
    def patch(self, request, task_id: str, item_id: str):
        _require_workspace_scope_query(request)
        serializer = WorkspaceTaskChecklistPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee_id = data.resolve_employee_id_for_username(request.user.username)
        actor_name, actor_role = _workspace_actor(request)
        data.patch_workspace_task_checklist_item(employee_id, task_id, item_id, serializer.validated_data)
        data.append_workspace_task_audit(
            employee_id,
            task_id,
            "updated",
            actor_name,
            actor_role,
            "Checklist item updated",
        )
        return Response(status=204)

    @extend_schema(
        operation_id="workspaceTaskChecklistDelete",
        parameters=[
            OpenApiParameter("building_id", OpenApiTypes.STR, required=True),
            OpenApiParameter("floor_id", OpenApiTypes.STR, required=True),
        ],
    )
    def delete(self, request, task_id: str, item_id: str):
        _require_workspace_scope_query(request)
        employee_id = data.resolve_employee_id_for_username(request.user.username)
        actor_name, actor_role = _workspace_actor(request)
        data.delete_workspace_task_checklist_item(employee_id, task_id, item_id)
        data.append_workspace_task_audit(
            employee_id,
            task_id,
            "updated",
            actor_name,
            actor_role,
            "Checklist item removed",
        )
        return Response(status=204)


class WorkspaceTaskAliasDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="workspaceTaskAliasDetail",
        parameters=[
            OpenApiParameter("building_id", OpenApiTypes.STR, required=True),
            OpenApiParameter("floor_id", OpenApiTypes.STR, required=True),
        ],
        responses=TaskSerializer,
    )
    def get(self, request, task_id: str):
        _require_workspace_scope_query(request)
        employee_id = data.resolve_employee_id_for_username(request.user.username)
        payload = data.get_workspace_task(employee_id, task_id)
        return Response(TaskSerializer(payload).data)

    @extend_schema(
        operation_id="workspaceTaskAliasPatch",
        parameters=[
            OpenApiParameter("building_id", OpenApiTypes.STR, required=True),
            OpenApiParameter("floor_id", OpenApiTypes.STR, required=True),
        ],
        request=WorkspaceTaskAliasPatchSerializer,
        responses=TaskSerializer,
    )
    def patch(self, request, task_id: str):
        _require_workspace_scope_query(request)
        serializer = WorkspaceTaskAliasPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee_id = data.resolve_employee_id_for_username(request.user.username)
        payload = data.patch_workspace_task(employee_id, task_id, serializer.validated_data)
        actor_name, actor_role = _workspace_actor(request)
        changed = ",".join(sorted(serializer.validated_data.keys())) or "updated"
        data.append_workspace_task_audit(employee_id, task_id, "updated", actor_name, actor_role, changed)
        return Response(TaskSerializer(payload).data)

    @extend_schema(
        operation_id="workspaceTaskAliasDelete",
        parameters=[
            OpenApiParameter("building_id", OpenApiTypes.STR, required=True),
            OpenApiParameter("floor_id", OpenApiTypes.STR, required=True),
        ],
        responses={204: None},
    )
    def delete(self, request, task_id: str):
        _require_workspace_scope_query(request)
        employee_id = data.resolve_employee_id_for_username(request.user.username)
        actor_name, actor_role = _workspace_actor(request)
        data.append_workspace_task_audit(employee_id, task_id, "deleted", actor_name, actor_role, "Task deleted")
        data.delete_workspace_task(employee_id, task_id)
        return Response(status=204)


def _require_workspace_path(building_id: str, _floor_id: str) -> None:
    data.get_building(building_id)


def _employee_for_building_path(request, building_id: str, floor_id: str) -> str:
    _require_workspace_path(building_id, floor_id)
    return data.resolve_employee_id_for_username(request.user.username)


class WorkspaceTaskBuildingAuditView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="workspaceTaskBuildingAuditList")
    def get(self, request, building_id: str, floor_id: str, task_id: str):
        employee_id = _employee_for_building_path(request, building_id, floor_id)
        payload = data.list_workspace_task_audit_events(employee_id, task_id)
        return Response(payload)


class WorkspaceTaskBuildingCommentsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="workspaceTaskBuildingCommentsList")
    def get(self, request, building_id: str, floor_id: str, task_id: str):
        employee_id = _employee_for_building_path(request, building_id, floor_id)
        payload = data.list_workspace_task_comments(employee_id, task_id)
        return Response(payload)

    @extend_schema(
        operation_id="workspaceTaskBuildingCommentsCreate",
        request=WorkspaceTaskCommentCreateSerializer,
    )
    def post(self, request, building_id: str, floor_id: str, task_id: str):
        serializer = WorkspaceTaskCommentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee_id = _employee_for_building_path(request, building_id, floor_id)
        actor_name, actor_role = _workspace_actor(request)
        data.add_workspace_task_comment(
            employee_id,
            task_id,
            serializer.validated_data["message"],
            actor_name,
            actor_role,
        )
        data.append_workspace_task_audit(
            employee_id,
            task_id,
            "commented",
            actor_name,
            actor_role,
            "Comment added",
        )
        return Response(status=204)


class WorkspaceTaskBuildingChecklistView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="workspaceTaskBuildingChecklistList")
    def get(self, request, building_id: str, floor_id: str, task_id: str):
        employee_id = _employee_for_building_path(request, building_id, floor_id)
        payload = data.list_workspace_task_checklist(employee_id, task_id)
        return Response(payload)

    @extend_schema(
        operation_id="workspaceTaskBuildingChecklistCreate",
        request=WorkspaceTaskChecklistCreateSerializer,
    )
    def post(self, request, building_id: str, floor_id: str, task_id: str):
        serializer = WorkspaceTaskChecklistCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee_id = _employee_for_building_path(request, building_id, floor_id)
        actor_name, actor_role = _workspace_actor(request)
        data.add_workspace_task_checklist_item(employee_id, task_id, serializer.validated_data["title"])
        data.append_workspace_task_audit(
            employee_id,
            task_id,
            "updated",
            actor_name,
            actor_role,
            "Checklist item added",
        )
        return Response(status=204)


class WorkspaceTaskBuildingChecklistItemView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="workspaceTaskBuildingChecklistPatch",
        request=WorkspaceTaskChecklistPatchSerializer,
    )
    def patch(self, request, building_id: str, floor_id: str, task_id: str, item_id: str):
        serializer = WorkspaceTaskChecklistPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee_id = _employee_for_building_path(request, building_id, floor_id)
        actor_name, actor_role = _workspace_actor(request)
        data.patch_workspace_task_checklist_item(employee_id, task_id, item_id, serializer.validated_data)
        data.append_workspace_task_audit(
            employee_id,
            task_id,
            "updated",
            actor_name,
            actor_role,
            "Checklist item updated",
        )
        return Response(status=204)

    @extend_schema(operation_id="workspaceTaskBuildingChecklistDelete")
    def delete(self, request, building_id: str, floor_id: str, task_id: str, item_id: str):
        employee_id = _employee_for_building_path(request, building_id, floor_id)
        actor_name, actor_role = _workspace_actor(request)
        data.delete_workspace_task_checklist_item(employee_id, task_id, item_id)
        data.append_workspace_task_audit(
            employee_id,
            task_id,
            "updated",
            actor_name,
            actor_role,
            "Checklist item removed",
        )
        return Response(status=204)
