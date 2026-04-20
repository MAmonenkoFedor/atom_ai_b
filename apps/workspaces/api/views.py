from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.workspaces import data

from .serializers import (
    BuildingDetailSerializer,
    BuildingListItemSerializer,
    DepartmentSerializer,
    EmployeeProfileSerializer,
    EmployeeOwnerProfileSerializer,
    EmployeePublicProfileSerializer,
    EmployeeWorkspaceContextSerializer,
    QuickTaskCreateResponseSerializer,
    QuickTaskCreateSerializer,
    UpdateMyEmployeeProfileSerializer,
    WorkspaceEmployeeCabinetSerializer,
    WorkspaceSerializer,
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
    if role_code in {"employee", "manager", "company_admin", "executive", "super_admin"}:
        return role_code
    return "employee"


class EmployeeWorkspaceCabinetView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="employeeWorkspaceCabinet", responses=WorkspaceEmployeeCabinetSerializer)
    def get(self, request):
        employee_id = data.resolve_employee_id_for_username(request.user.username)
        viewer_role = _resolve_viewer_role(request.user)
        payload = data.get_employee_workspace(employee_id, viewer_role)
        return Response(WorkspaceEmployeeCabinetSerializer(payload).data)


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
        responses={200: EmployeeOwnerProfileSerializer},
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
        return Response(QuickTaskCreateResponseSerializer(payload).data, status=201)
