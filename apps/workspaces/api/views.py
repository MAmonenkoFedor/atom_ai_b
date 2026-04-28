from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, PolymorphicProxySerializer, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.service import emit_audit_event
from apps.audit.models import AuditEvent
from apps.identity.api.serializers import SessionUserSerializer
from apps.orgstructure.models import OrgUnit
from apps.projects.models import Project
from apps.workspaces import data, documents_service

from .serializers import (
    BuildingDetailSerializer,
    BuildingListItemSerializer,
    DepartmentSerializer,
    DocumentSerializer,
    EmployeeProfileSerializer,
    EmployeeOwnerProfileSerializer,
    EmployeeNotificationListSerializer,
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


_CAREER_EVENT_TITLE_MAP = {
    "joined_department": "Вас добавили в отдел",
    "left_department": "Вас убрали из отдела",
    "transferred_department": "Вас перевели в другой отдел",
    "became_department_lead": "Вас назначили главой отдела",
    "removed_as_department_lead": "С вас сняли роль главы отдела",
    "assigned_to_project": "Вас добавили в проект",
    "removed_from_project": "Вас убрали из проекта",
    "became_project_lead": "Вас назначили ответственным за проект",
    "removed_as_project_lead": "С вас сняли роль ответственного за проект",
    "project_role_changed": "Вам изменили роль в проекте",
    "manager_changed": "Вам изменили руководителя",
    "job_title_changed": "Вам изменили должность",
    "system_role_changed": "Вам изменили системную роль",
}


def _notification_targets_user(event: AuditEvent, user_id: int) -> bool:
    uid = str(user_id)
    if event.entity_type == "employee" and str(event.entity_id or "") == uid:
        return True
    payload = event.payload or {}
    if not isinstance(payload, dict):
        return False
    for key in ("user_id", "subject_user_id", "employee_id", "member_user_id", "target_user_id"):
        raw = payload.get(key)
        if raw is None:
            continue
        if str(raw).strip() == uid:
            return True
    return False


def _notification_title(event: AuditEvent, project_names: dict[str, str], org_unit_names: dict[str, str]) -> str:
    event_type = event.event_type or ""
    payload = event.payload or {}

    if event_type.startswith("career."):
        suffix = event_type.split("career.", 1)[1]
        base = _CAREER_EVENT_TITLE_MAP.get(suffix, "Обновление в вашей карьере")
        if suffix in {"joined_department", "transferred_department", "became_department_lead"}:
            org_unit_id = str(payload.get("org_unit_id") or event.department_id or "").strip()
            if org_unit_id and org_unit_id in org_unit_names:
                return f"{base}: {org_unit_names[org_unit_id]}"
        if suffix in {"assigned_to_project", "became_project_lead", "project_role_changed"}:
            project_id = str(event.project_id or "").strip()
            if project_id and project_id in project_names:
                return f"{base}: {project_names[project_id]}"
        return base

    if event_type == "project.project_lead_set":
        project_id = str(event.project_id or "").strip()
        if project_id and project_id in project_names:
            return f"Вас назначили ответственным за проект: {project_names[project_id]}"
        return "Вас назначили ответственным за проект"
    if event_type == "project.project_lead_cleared":
        return "С вас сняли ответственность за проект"
    if event_type == "project.member_upserted":
        project_id = str(event.project_id or "").strip()
        if project_id and project_id in project_names:
            return f"Вас добавили в проект: {project_names[project_id]}"
        return "Вас добавили в проект"
    if event_type == "project.member_deleted":
        return "Вас удалили из проекта"
    if event_type == "org.department_lead_set":
        org_unit_id = str(payload.get("org_unit_id") or event.department_id or "").strip()
        if org_unit_id and org_unit_id in org_unit_names:
            return f"Вас назначили главой отдела: {org_unit_names[org_unit_id]}"
        return "Вас назначили главой отдела"
    if event_type == "org.department_lead_cleared":
        return "С вас сняли роль главы отдела"
    if event_type == "org.department_membership_changed":
        to_dep = str(payload.get("to_department_id") or "").strip()
        from_dep = str(payload.get("from_department_id") or "").strip()
        if to_dep and to_dep in org_unit_names:
            return f"Вас добавили в отдел: {org_unit_names[to_dep]}"
        if from_dep and from_dep in org_unit_names:
            return f"Вас убрали из отдела: {org_unit_names[from_dep]}"
        return "Изменили ваше назначение в отдел"

    return "Изменение доступа или роли"


def _notification_description(event: AuditEvent) -> str:
    actor = event.actor
    actor_name = "Система"
    if actor is not None:
        actor_name = (actor.get_full_name() or actor.username or "").strip() or "Система"
    return f"Источник: {actor_name}"


def _notification_href(event: AuditEvent) -> str:
    if event.project_id:
        return f"/app/projects/{event.project_id}"
    if event.task_id:
        return f"/app/tasks/{event.task_id}"
    return "/app/employee/me"


def _collect_employee_notifications(user, limit: int = 25) -> list[dict]:
    candidate_events = list(
        AuditEvent.objects.select_related("actor")
        .filter(
            Q(event_type__startswith="career.")
            | Q(event_type__in=[
                "project.project_lead_set",
                "project.project_lead_cleared",
                "project.member_upserted",
                "project.member_deleted",
                "org.department_lead_set",
                "org.department_lead_cleared",
                "org.department_membership_changed",
            ])
        )
        .order_by("-created_at")[:400]
    )
    relevant = [event for event in candidate_events if _notification_targets_user(event, user.id)]
    relevant = relevant[: max(1, min(limit, 100))]

    project_ids = sorted({str(event.project_id).strip() for event in relevant if str(event.project_id or "").strip()})
    org_unit_ids: set[str] = set()
    for event in relevant:
        if str(event.department_id or "").strip():
            org_unit_ids.add(str(event.department_id).strip())
        payload = event.payload or {}
        if isinstance(payload, dict):
            raw = payload.get("org_unit_id") or payload.get("to_department_id") or payload.get("from_department_id")
            if raw is not None and str(raw).strip():
                org_unit_ids.add(str(raw).strip())

    project_names = {
        str(row["id"]): row["name"]
        for row in Project.objects.filter(id__in=project_ids).values("id", "name")
    }
    org_unit_names = {
        str(row["id"]): row["name"]
        for row in OrgUnit.objects.filter(id__in=sorted(org_unit_ids)).values("id", "name")
    }

    return [
        {
            "id": str(event.id),
            "event_type": event.event_type,
            "title": _notification_title(event, project_names, org_unit_names),
            "description": _notification_description(event),
            "created_at": event.created_at.isoformat() if event.created_at else "",
            "href": _notification_href(event),
        }
        for event in relevant
    ]


def _split_name(full_name: str) -> tuple[str, str]:
    parts = [p for p in (full_name or "").strip().split(" ") if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _hydrate_owner_profile_for_user(payload: dict, user) -> dict:
    header = payload.setdefault("header", {})
    contacts = payload.setdefault("contacts", {})

    existing_full_name = str(header.get("full_name") or "").strip()
    first_name = (getattr(user, "first_name", "") or "").strip()
    last_name = (getattr(user, "last_name", "") or "").strip()
    if not first_name or not last_name:
        fallback_first, fallback_last = _split_name(existing_full_name)
        first_name = first_name or fallback_first
        last_name = last_name or fallback_last

    full_name = f"{first_name} {last_name}".strip() or existing_full_name or user.username
    header["first_name"] = first_name
    header["last_name"] = last_name
    header["full_name"] = full_name

    work_email = (getattr(user, "email", "") or "").strip()
    if work_email:
        contacts["work_email"] = work_email

    session_user = SessionUserSerializer(user).data
    department = (session_user.get("department") or "").strip()
    if department:
        header["department"] = department
    title = (session_user.get("job_title") or "").strip()
    if title:
        header["title"] = title
    return payload


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
        payload = _hydrate_owner_profile_for_user(payload, request.user)
        return Response(EmployeeOwnerProfileSerializer(payload).data)

    @extend_schema(
        operation_id="employeeMeProfilePatch",
        request=UpdateMyEmployeeProfileSerializer,
        responses=EmployeeOwnerProfileSerializer,
    )
    def patch(self, request):
        serializer = UpdateMyEmployeeProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = dict(serializer.validated_data)

        user = request.user
        changed_user_fields: list[str] = []
        if "first_name" in validated:
            user.first_name = (validated["first_name"] or "").strip()
            changed_user_fields.append("first_name")
        if "last_name" in validated:
            user.last_name = (validated["last_name"] or "").strip()
            changed_user_fields.append("last_name")
        if changed_user_fields:
            user.save(update_fields=changed_user_fields)

        employee_id = data.resolve_employee_id_for_username(request.user.username)
        payload = data.patch_employee_owner_profile(employee_id, validated)
        payload = _hydrate_owner_profile_for_user(payload, request.user)
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


class EmployeeMeNotificationsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="employeeMeNotifications",
        responses=EmployeeNotificationListSerializer,
    )
    def get(self, request):
        try:
            limit = int(request.query_params.get("limit") or 25)
        except (TypeError, ValueError):
            limit = 25
        notifications = _collect_employee_notifications(request.user, limit=limit)
        return Response({"count": len(notifications), "results": notifications})


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
