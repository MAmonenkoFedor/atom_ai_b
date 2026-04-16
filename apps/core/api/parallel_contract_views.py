from datetime import datetime
from itertools import count

from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
)
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsCompanyAdminOrSuperAdmin, IsSuperAdmin

CURSOR_PARAM_DESCRIPTION = (
    "Cursor-based pagination token. "
    "Format: `YYYY-MM-DDTHH:MM:SSZ::<id>`. "
    "Pass empty cursor (`cursor=`) for the first page. "
    "Use `next_cursor` from response to request the next page."
)

CURSOR_MODE_DESCRIPTION = (
    "When `cursor` is provided, endpoint uses cursor pagination with stable ordering "
    "(`timestamp/created_at` desc, then `id` desc). "
    "When `cursor` is not provided, classic `page/page_size` mode is used."
)


class CompanyAdminOverviewSerializer(serializers.Serializer):
    users_count = serializers.IntegerField()
    departments_count = serializers.IntegerField()
    invites_pending = serializers.IntegerField()


class CompanyDepartmentSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    status = serializers.ChoiceField(choices=["green", "yellow", "red"])


class CompanyUserSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=["employee", "manager", "company_admin"])
    status = serializers.ChoiceField(choices=["active", "invited", "blocked"])
    department_id = serializers.IntegerField()


class CompanyUserListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    results = CompanyUserSummarySerializer(many=True)


class CompanyInviteSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=["employee", "manager", "company_admin"])
    status = serializers.ChoiceField(choices=["pending", "accepted", "expired", "revoked"])
    created_at = serializers.DateTimeField()


class CompanyInviteListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    results = CompanyInviteSerializer(many=True)


class CreateCompanyInviteRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=["employee", "manager", "company_admin"], required=False, default="employee"
    )


class UpdateCompanyUserRoleRequestSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["employee", "manager", "company_admin"])


class SuperAdminOverviewSerializer(serializers.Serializer):
    tenants_count = serializers.IntegerField()
    platform_users_count = serializers.IntegerField()
    invites_pending = serializers.IntegerField()


class TenantSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    status = serializers.ChoiceField(choices=["active", "trial", "suspended"])


class TenantListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    results = TenantSummarySerializer(many=True)


class CreateTenantRequestSerializer(serializers.Serializer):
    name = serializers.CharField()


class UpdateTenantStatusRequestSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["active", "trial", "suspended"])


class PlatformUserSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=["platform_admin", "support", "security"])


class PlatformUserListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    results = PlatformUserSummarySerializer(many=True)


class PlatformInviteSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=["platform_admin", "support", "security"])
    status = serializers.ChoiceField(choices=["pending", "accepted", "expired", "revoked"])
    created_at = serializers.DateTimeField()


class PlatformInviteListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    results = PlatformInviteSerializer(many=True)


class CreatePlatformInviteRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=["platform_admin", "support", "security"], required=False, default="support"
    )


class PlatformAuditStatsSerializer(serializers.Serializer):
    total_events = serializers.IntegerField()
    failed_events = serializers.IntegerField()
    critical_events = serializers.IntegerField()


class PlatformAuditEventSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    timestamp = serializers.DateTimeField()
    tenant_id = serializers.IntegerField()
    action = serializers.CharField()
    severity = serializers.ChoiceField(choices=["low", "medium", "high", "critical"])
    status = serializers.ChoiceField(choices=["success", "failed"])
    actor_type = serializers.ChoiceField(choices=["user", "system", "integration"])
    message = serializers.CharField()


class PlatformAuditListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    results = PlatformAuditEventSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    next_cursor = serializers.CharField(allow_null=True)


class AdminActionStatsSerializer(serializers.Serializer):
    total_events = serializers.IntegerField()
    failed_events = serializers.IntegerField()
    critical_events = serializers.IntegerField()


class AdminActionEventSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    timestamp = serializers.DateTimeField()
    scope = serializers.ChoiceField(choices=["company", "platform"])
    severity = serializers.ChoiceField(choices=["low", "medium", "high", "critical"])
    status = serializers.ChoiceField(choices=["success", "failed"])
    action = serializers.CharField()
    actor = serializers.CharField()
    details = serializers.DictField()


class AdminActionListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    results = AdminActionEventSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    next_cursor = serializers.CharField(allow_null=True)


class ErrorDetailSerializer(serializers.Serializer):
    detail = serializers.CharField()


class TaskSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    status = serializers.ChoiceField(choices=["todo", "in_progress", "done"])
    priority = serializers.ChoiceField(choices=["high", "medium", "low"])
    project_id = serializers.IntegerField(allow_null=True)
    assignee_id = serializers.IntegerField()
    department_id = serializers.IntegerField(allow_null=True)
    due_date = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class TaskListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    num_pages = serializers.IntegerField()
    next_cursor = serializers.CharField(allow_null=True)
    results = TaskSerializer(many=True)


class TaskBoardResponseSerializer(serializers.Serializer):
    todo = TaskSerializer(many=True)
    in_progress = TaskSerializer(many=True)
    done = TaskSerializer(many=True)


class TaskActivityEventSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    task_id = serializers.IntegerField()
    event_type = serializers.CharField()
    actor_id = serializers.IntegerField(allow_null=True)
    actor_username = serializers.CharField(allow_blank=True)
    payload = serializers.DictField()
    created_at = serializers.DateTimeField()


class TaskActivityListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    num_pages = serializers.IntegerField()
    next_cursor = serializers.CharField(allow_null=True)
    results = TaskActivityEventSerializer(many=True)


class TaskStatsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    todo = serializers.IntegerField()
    in_progress = serializers.IntegerField()
    done = serializers.IntegerField()
    high_priority = serializers.IntegerField()
    medium_priority = serializers.IntegerField()
    low_priority = serializers.IntegerField()


class CreateTaskRequestSerializer(serializers.Serializer):
    title = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(
        choices=["todo", "in_progress", "done"], required=False, default="todo"
    )
    priority = serializers.ChoiceField(
        choices=["high", "medium", "low"], required=False, default="medium"
    )
    project_id = serializers.IntegerField(required=False, allow_null=True)
    assignee_id = serializers.IntegerField()
    department_id = serializers.IntegerField(required=False, allow_null=True)
    due_date = serializers.DateTimeField(required=False, allow_null=True)

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError("This field may not be blank.")
        return value.strip()


class UpdateTaskRequestSerializer(serializers.Serializer):
    title = serializers.CharField(required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=["todo", "in_progress", "done"], required=False)
    priority = serializers.ChoiceField(choices=["high", "medium", "low"], required=False)
    project_id = serializers.IntegerField(required=False, allow_null=True)
    assignee_id = serializers.IntegerField(required=False)
    department_id = serializers.IntegerField(required=False, allow_null=True)
    due_date = serializers.DateTimeField(required=False, allow_null=True)

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError("This field may not be blank.")
        return value.strip()


class BulkTaskStatusRequestSerializer(serializers.Serializer):
    task_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    status = serializers.ChoiceField(choices=["todo", "in_progress", "done"])

    def validate_task_ids(self, value):
        if any(task_id <= 0 for task_id in value):
            raise serializers.ValidationError("task_ids must contain positive integers.")
        if len(set(value)) != len(value):
            raise serializers.ValidationError("task_ids must be unique.")
        return value


class BulkTaskAssignRequestSerializer(serializers.Serializer):
    task_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    assignee_id = serializers.IntegerField()

    def validate_task_ids(self, value):
        if any(task_id <= 0 for task_id in value):
            raise serializers.ValidationError("task_ids must contain positive integers.")
        if len(set(value)) != len(value):
            raise serializers.ValidationError("task_ids must be unique.")
        return value


class BulkTaskUpdateResponseSerializer(serializers.Serializer):
    updated = serializers.IntegerField()
    not_found_ids = serializers.ListField(child=serializers.IntegerField())
    results = TaskSerializer(many=True)


_company_invite_seq = count(1001)
_platform_invite_seq = count(2001)
_tenant_seq = count(301)

COMPANY_DEPARTMENTS = [
    {"id": 1, "name": "Engineering", "status": "green"},
    {"id": 2, "name": "Marketing", "status": "yellow"},
    {"id": 3, "name": "Support", "status": "green"},
]

COMPANY_USERS = [
    {
        "id": 11,
        "name": "Alex Kim",
        "email": "alex@company.com",
        "role": "company_admin",
        "status": "active",
        "department_id": 1,
    },
    {
        "id": 12,
        "name": "Mila Stone",
        "email": "mila@company.com",
        "role": "manager",
        "status": "active",
        "department_id": 2,
    },
    {
        "id": 13,
        "name": "Chris Vale",
        "email": "chris@company.com",
        "role": "employee",
        "status": "invited",
        "department_id": 3,
    },
]

COMPANY_INVITES = [
    {
        "id": 501,
        "email": "new-hire@company.com",
        "role": "employee",
        "status": "pending",
        "created_at": "2026-04-15T08:00:00Z",
    }
]

PLATFORM_TENANTS = [
    {"id": 201, "name": "Acme", "status": "active"},
    {"id": 202, "name": "Northwind", "status": "trial"},
]

PLATFORM_USERS = [
    {"id": 901, "name": "Root Admin", "email": "root@platform.com", "role": "platform_admin"},
    {"id": 902, "name": "Sec Ops", "email": "sec@platform.com", "role": "security"},
]

PLATFORM_INVITES = [
    {
        "id": 801,
        "email": "support@platform.com",
        "role": "support",
        "status": "pending",
        "created_at": "2026-04-15T09:00:00Z",
    }
]

AUDIT_EVENTS = [
    {
        "id": 1,
        "timestamp": "2026-04-15T09:10:00Z",
        "tenant_id": 201,
        "action": "login",
        "severity": "low",
        "status": "success",
        "actor_type": "user",
        "message": "User login success",
    },
    {
        "id": 2,
        "timestamp": "2026-04-15T09:20:00Z",
        "tenant_id": 202,
        "action": "invite_revoke",
        "severity": "medium",
        "status": "failed",
        "actor_type": "integration",
        "message": "Revoke failed due to timeout",
    },
    {
        "id": 3,
        "timestamp": "2026-04-15T09:30:00Z",
        "tenant_id": 201,
        "action": "tenant_status_change",
        "severity": "high",
        "status": "success",
        "actor_type": "system",
        "message": "Tenant moved to active",
    },
]

ADMIN_ACTION_EVENTS = [
    {
        "id": 101,
        "timestamp": "2026-04-15T10:00:00Z",
        "scope": "company",
        "severity": "medium",
        "status": "success",
        "action": "user_role_update",
        "actor": "admin@company.com",
        "details": {
            "target_user_id": 13,
            "old_role": "employee",
            "new_role": "manager",
        },
    },
    {
        "id": 102,
        "timestamp": "2026-04-15T10:10:00Z",
        "scope": "platform",
        "severity": "high",
        "status": "failed",
        "action": "tenant_status_change",
        "actor": "root@platform.com",
        "details": {
            "tenant_id": 202,
            "requested_status": "active",
            "error": "permission_check_failed",
        },
    },
    {
        "id": 103,
        "timestamp": "2026-04-15T10:20:00Z",
        "scope": "platform",
        "severity": "critical",
        "status": "success",
        "action": "policy_override",
        "actor": "security@platform.com",
        "details": {
            "policy_key": "max_parallel_invites",
            "old_value": 100,
            "new_value": 20,
        },
    },
]

TASK_ITEMS = [
    {
        "id": 2001,
        "title": "Prepare sprint board",
        "description": "Sync priorities with frontend",
        "status": "in_progress",
        "priority": "high",
        "project_id": 1,
        "assignee_id": 12,
        "department_id": 1,
        "due_date": "2026-04-20T12:00:00Z",
        "created_at": "2026-04-15T09:00:00Z",
        "updated_at": "2026-04-15T09:30:00Z",
    },
    {
        "id": 2002,
        "title": "Review company invites flow",
        "description": "",
        "status": "todo",
        "priority": "medium",
        "project_id": 2,
        "assignee_id": 11,
        "department_id": 2,
        "due_date": None,
        "created_at": "2026-04-15T10:00:00Z",
        "updated_at": "2026-04-15T10:00:00Z",
    },
]
_task_seq = count(max(item["id"] for item in TASK_ITEMS) + 1)
_task_activity_seq = count(1)
TASK_ACTIVITY_EVENTS = []


def _contains(value, needle):
    return needle.lower() in str(value).lower()


def _invalid_enum_detail(field_name, allowed_values):
    allowed = ", ".join(allowed_values)
    return f"Invalid {field_name}. Allowed: {allowed}."


def _validate_query_enum(value, field_name, allowed_values):
    if value is None or str(value).strip() == "":
        return None
    normalized = str(value).strip()
    if normalized not in allowed_values:
        raise ValidationError({"detail": _invalid_enum_detail(field_name, allowed_values)})
    return normalized


def _to_int(value, field_name):
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"detail": f"Invalid {field_name}."}) from exc


def _apply_audit_filters(params, items):
    filtered = items
    q = params.get("q")
    tenant_id = params.get("tenant_id")
    action = params.get("action")
    severity = _validate_query_enum(
        params.get("severity"), "severity", ["low", "medium", "high", "critical"]
    )
    status_param = _validate_query_enum(params.get("status"), "status", ["success", "failed"])
    from_param = params.get("from")
    to_param = params.get("to")

    if q:
        filtered = [
            e
            for e in filtered
            if _contains(e["message"], q) or _contains(e["action"], q) or _contains(e["id"], q)
        ]
    if tenant_id:
        filtered = [e for e in filtered if e["tenant_id"] == _to_int(tenant_id, "tenant_id")]
    if action:
        filtered = [e for e in filtered if e["action"] == action]
    if severity:
        filtered = [e for e in filtered if e["severity"] == severity]
    if status_param:
        filtered = [e for e in filtered if e["status"] == status_param]
    if from_param:
        from_dt = datetime.fromisoformat(from_param.replace("Z", "+00:00"))
        filtered = [
            e
            for e in filtered
            if datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")) >= from_dt
        ]
    if to_param:
        to_dt = datetime.fromisoformat(to_param.replace("Z", "+00:00"))
        filtered = [
            e
            for e in filtered
            if datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")) <= to_dt
        ]
    return filtered


def _apply_admin_action_filters(params, items):
    filtered = items
    q = params.get("q")
    scope = _validate_query_enum(params.get("scope"), "scope", ["company", "platform"])
    severity = _validate_query_enum(
        params.get("severity"), "severity", ["low", "medium", "high", "critical"]
    )
    status_param = _validate_query_enum(params.get("status"), "status", ["success", "failed"])
    action = params.get("action")
    actor = params.get("actor")
    from_param = params.get("from")
    to_param = params.get("to")

    if q:
        filtered = [
            e
            for e in filtered
            if _contains(e["action"], q)
            or _contains(e["actor"], q)
            or _contains(e["id"], q)
            or _contains(e["details"], q)
        ]
    if scope:
        filtered = [e for e in filtered if e["scope"] == scope]
    if severity:
        filtered = [e for e in filtered if e["severity"] == severity]
    if status_param:
        filtered = [e for e in filtered if e["status"] == status_param]
    if action:
        filtered = [e for e in filtered if e["action"] == action]
    if actor:
        filtered = [e for e in filtered if _contains(e["actor"], actor)]
    if from_param:
        from_dt = datetime.fromisoformat(from_param.replace("Z", "+00:00"))
        filtered = [
            e
            for e in filtered
            if datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")) >= from_dt
        ]
    if to_param:
        to_dt = datetime.fromisoformat(to_param.replace("Z", "+00:00"))
        filtered = [
            e
            for e in filtered
            if datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")) <= to_dt
        ]
    return filtered


def _find_task(task_id: int):
    for task in TASK_ITEMS:
        if task["id"] == task_id:
            return task
    return None


def _company_user_department_map():
    return {int(user["id"]): user.get("department_id") for user in COMPANY_USERS}


def _company_department_ids():
    return {int(dep["id"]) for dep in COMPANY_DEPARTMENTS}


def _validate_task_relations(task):
    errors = {}
    user_department = _company_user_department_map()
    department_ids = _company_department_ids()

    assignee_id = task.get("assignee_id")
    if assignee_id not in user_department:
        errors["assignee_id"] = "Unknown assignee_id."

    department_id = task.get("department_id")
    if department_id is not None and department_id not in department_ids:
        errors["department_id"] = "Unknown department_id."

    project_id = task.get("project_id")
    if project_id is not None and int(project_id) <= 0:
        errors["project_id"] = "project_id must be a positive integer or null."

    if assignee_id in user_department and department_id is not None:
        expected_department = user_department[assignee_id]
        if expected_department is not None and expected_department != department_id:
            errors["department_id"] = "department_id must match assignee_id department."

    if errors:
        raise ValidationError(errors)


def _add_task_activity(task_id, event_type, request, payload):
    user = getattr(request, "user", None)
    actor_id = user.id if user and getattr(user, "is_authenticated", False) else None
    actor_username = user.username if actor_id is not None else ""
    event = {
        "id": next(_task_activity_seq),
        "task_id": task_id,
        "event_type": event_type,
        "actor_id": actor_id,
        "actor_username": actor_username,
        "payload": payload,
        "created_at": timezone.now().isoformat().replace("+00:00", "Z"),
    }
    TASK_ACTIVITY_EVENTS.append(event)


def _task_activity_for(task_id: int):
    return [event for event in TASK_ACTIVITY_EVENTS if event["task_id"] == task_id]


def _apply_task_filters(params, items):
    tasks = items
    q = params.get("q")
    status_param = _validate_query_enum(
        params.get("status"), "status", ["todo", "in_progress", "done"]
    )
    priority = _validate_query_enum(
        params.get("priority"), "priority", ["high", "medium", "low"]
    )
    project_id = params.get("project_id")
    assignee_id = params.get("assignee_id")
    department_id = params.get("department_id")
    updated_at_from = _parse_iso_datetime_param(params.get("updated_at_from"), "updated_at_from")
    updated_at_to = _parse_iso_datetime_param(params.get("updated_at_to"), "updated_at_to")

    if q:
        tasks = [
            t
            for t in tasks
            if _contains(t["title"], q) or _contains(t["description"], q) or _contains(t["id"], q)
        ]
    if status_param:
        tasks = [t for t in tasks if t["status"] == status_param]
    if priority:
        tasks = [t for t in tasks if t["priority"] == priority]
    if project_id:
        tasks = [t for t in tasks if t["project_id"] == _to_int(project_id, "project_id")]
    if assignee_id:
        tasks = [t for t in tasks if t["assignee_id"] == _to_int(assignee_id, "assignee_id")]
    if department_id:
        dep_id = _to_int(department_id, "department_id")
        tasks = [t for t in tasks if t["department_id"] == dep_id]
    if updated_at_from:
        tasks = [
            t
            for t in tasks
            if datetime.fromisoformat(t["updated_at"].replace("Z", "+00:00")) >= updated_at_from
        ]
    if updated_at_to:
        tasks = [
            t
            for t in tasks
            if datetime.fromisoformat(t["updated_at"].replace("Z", "+00:00")) <= updated_at_to
        ]

    return tasks


def _paginate_items(items, params, *, default_page_size=20, max_page_size=200):
    page = _to_int(params.get("page", "1"), "page")
    page_size = _to_int(params.get("page_size", str(default_page_size)), "page_size")
    if page < 1 or page_size < 1:
        raise ValidationError({"detail": "page and page_size must be positive integers."})
    page_size = min(page_size, max_page_size)
    count = len(items)
    num_pages = max(1, ((count - 1) // page_size) + 1)
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], page, page_size, count, num_pages


def _sort_tasks(items, sort_param):
    allowed = {
        "id",
        "-id",
        "created_at",
        "-created_at",
        "updated_at",
        "-updated_at",
        "due_date",
        "-due_date",
        "priority",
        "-priority",
        "status",
        "-status",
        "title",
        "-title",
    }
    if sort_param not in allowed:
        raise ValidationError(
            {
                "detail": (
                    "Invalid sort. Allowed: id, -id, created_at, -created_at, "
                    "updated_at, -updated_at, due_date, -due_date, priority, -priority, "
                    "status, -status, title, -title."
                )
            }
        )

    reverse = sort_param.startswith("-")
    field = sort_param[1:] if reverse else sort_param
    priority_order = {"high": 0, "medium": 1, "low": 2}
    status_order = {"todo": 0, "in_progress": 1, "done": 2}

    def _key(task):
        value = task.get(field)
        if field == "priority":
            return priority_order.get(value, 99)
        if field == "status":
            return status_order.get(value, 99)
        if field in {"due_date", "created_at", "updated_at"}:
            return (value is None, value or "")
        if value is None:
            return ""
        return value

    return sorted(items, key=_key, reverse=reverse)


def _parse_iso_datetime_param(raw_value, field_name):
    if raw_value is None or str(raw_value).strip() == "":
        return None
    try:
        return datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(
            {"detail": f"Invalid {field_name}. Use ISO datetime, e.g. 2026-04-15T10:00:00Z."}
        ) from exc


def _parse_tasks_cursor(raw_cursor):
    if raw_cursor is None or str(raw_cursor).strip() == "":
        return None, None
    normalized = str(raw_cursor).strip()
    try:
        dt_text, id_text = normalized.split("::", 1)
        cursor_dt = datetime.fromisoformat(dt_text.replace("Z", "+00:00"))
        cursor_id = int(id_text)
        return cursor_dt, cursor_id
    except (ValueError, TypeError) as exc:
        raise ValidationError(
            {
                "detail": (
                    "Invalid cursor. Expected format: "
                    "YYYY-MM-DDTHH:MM:SSZ::<task_id>."
                )
            }
        ) from exc


def _cursor_paginate_tasks(items, params):
    page_size = _to_int(params.get("page_size", "20"), "page_size")
    if page_size < 1:
        raise ValidationError({"detail": "page_size must be a positive integer."})
    page_size = min(page_size, 200)

    # Cursor mode always uses stable order: updated_at desc, id desc.
    ordered = sorted(items, key=lambda t: (t["updated_at"], t["id"]), reverse=True)
    cursor_dt, cursor_id = _parse_tasks_cursor(params.get("cursor"))
    if cursor_dt is not None:
        filtered = []
        for task in ordered:
            task_dt = datetime.fromisoformat(task["updated_at"].replace("Z", "+00:00"))
            if (task_dt < cursor_dt) or (task_dt == cursor_dt and task["id"] < cursor_id):
                filtered.append(task)
        ordered = filtered

    results = ordered[:page_size]
    if len(results) == page_size:
        last = results[-1]
        next_cursor = f"{last['updated_at']}::{last['id']}"
    else:
        next_cursor = None

    return results, page_size, next_cursor


def _parse_activity_cursor(raw_cursor):
    if raw_cursor is None or str(raw_cursor).strip() == "":
        return None, None
    normalized = str(raw_cursor).strip()
    try:
        dt_text, id_text = normalized.split("::", 1)
        cursor_dt = datetime.fromisoformat(dt_text.replace("Z", "+00:00"))
        cursor_id = int(id_text)
        return cursor_dt, cursor_id
    except (ValueError, TypeError) as exc:
        raise ValidationError(
            {
                "detail": (
                    "Invalid cursor. Expected format: "
                    "YYYY-MM-DDTHH:MM:SSZ::<event_id>."
                )
            }
        ) from exc


def _cursor_paginate_activity(items, params):
    page_size = _to_int(params.get("page_size", "20"), "page_size")
    if page_size < 1:
        raise ValidationError({"detail": "page_size must be a positive integer."})
    page_size = min(page_size, 200)

    # Stable order for activity stream: created_at desc, id desc.
    ordered = sorted(items, key=lambda e: (e["created_at"], e["id"]), reverse=True)
    cursor_dt, cursor_id = _parse_activity_cursor(params.get("cursor"))
    if cursor_dt is not None:
        filtered = []
        for event in ordered:
            event_dt = datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
            if (event_dt < cursor_dt) or (event_dt == cursor_dt and event["id"] < cursor_id):
                filtered.append(event)
        ordered = filtered

    results = ordered[:page_size]
    if len(results) == page_size:
        last = results[-1]
        next_cursor = f"{last['created_at']}::{last['id']}"
    else:
        next_cursor = None

    return results, page_size, next_cursor


def _parse_event_cursor(raw_cursor):
    if raw_cursor is None or str(raw_cursor).strip() == "":
        return None, None
    normalized = str(raw_cursor).strip()
    try:
        dt_text, id_text = normalized.split("::", 1)
        cursor_dt = datetime.fromisoformat(dt_text.replace("Z", "+00:00"))
        cursor_id = int(id_text)
        return cursor_dt, cursor_id
    except (ValueError, TypeError) as exc:
        raise ValidationError(
            {
                "detail": (
                    "Invalid cursor. Expected format: "
                    "YYYY-MM-DDTHH:MM:SSZ::<event_id>."
                )
            }
        ) from exc


def _cursor_paginate_events(items, params):
    page_size = _to_int(params.get("page_size", "20"), "page_size")
    if page_size < 1:
        raise ValidationError({"detail": "page_size must be a positive integer."})
    page_size = min(page_size, 200)

    ordered = sorted(items, key=lambda e: (e["timestamp"], e["id"]), reverse=True)
    cursor_dt, cursor_id = _parse_event_cursor(params.get("cursor"))
    if cursor_dt is not None:
        filtered = []
        for event in ordered:
            event_dt = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
            if (event_dt < cursor_dt) or (event_dt == cursor_dt and event["id"] < cursor_id):
                filtered.append(event)
        ordered = filtered

    results = ordered[:page_size]
    if len(results) == page_size:
        last = results[-1]
        next_cursor = f"{last['timestamp']}::{last['id']}"
    else:
        next_cursor = None

    return results, page_size, next_cursor


class CompanyAdminOverviewView(APIView):
    permission_classes = [IsCompanyAdminOrSuperAdmin]

    @extend_schema(
        operation_id="companyAdminOverview",
        responses=CompanyAdminOverviewSerializer,
    )
    def get(self, request):
        return Response(
            {
                "users_count": len(COMPANY_USERS),
                "departments_count": len(COMPANY_DEPARTMENTS),
                "invites_pending": len([x for x in COMPANY_INVITES if x["status"] == "pending"]),
            }
        )


class CompanyAdminDepartmentsView(APIView):
    permission_classes = [IsCompanyAdminOrSuperAdmin]

    @extend_schema(
        operation_id="companyAdminDepartmentsList",
        responses=CompanyDepartmentSummarySerializer(many=True),
    )
    def get(self, request):
        return Response(COMPANY_DEPARTMENTS)


class CompanyAdminUsersView(APIView):
    permission_classes = [IsCompanyAdminOrSuperAdmin]

    @extend_schema(
        operation_id="companyAdminUsersList",
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR),
            OpenApiParameter("role", OpenApiTypes.STR),
            OpenApiParameter("status", OpenApiTypes.STR),
            OpenApiParameter("department_id", OpenApiTypes.INT),
        ],
        responses=CompanyUserListResponseSerializer,
    )
    def get(self, request):
        q = request.query_params.get("q")
        role = _validate_query_enum(
            request.query_params.get("role"),
            "role",
            ["employee", "manager", "company_admin"],
        )
        status_param = _validate_query_enum(
            request.query_params.get("status"),
            "status",
            ["active", "invited", "blocked"],
        )
        department_id = request.query_params.get("department_id")

        users = COMPANY_USERS
        if q:
            users = [u for u in users if _contains(u["name"], q) or _contains(u["email"], q)]
        if role:
            users = [u for u in users if u["role"] == role]
        if status_param:
            users = [u for u in users if u["status"] == status_param]
        if department_id:
            users = [u for u in users if u["department_id"] == _to_int(department_id, "department_id")]
        return Response({"count": len(users), "results": users})


class CompanyAdminInvitesView(APIView):
    permission_classes = [IsCompanyAdminOrSuperAdmin]

    @extend_schema(
        operation_id="companyAdminInvitesList",
        responses=CompanyInviteListResponseSerializer,
    )
    def get(self, request):
        return Response({"count": len(COMPANY_INVITES), "results": COMPANY_INVITES})

    @extend_schema(
        operation_id="companyAdminInvitesCreate",
        request=CreateCompanyInviteRequestSerializer,
        responses={201: CompanyInviteSerializer, 400: ErrorDetailSerializer},
    )
    def post(self, request):
        serializer = CreateCompanyInviteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        invite = {
            "id": next(_company_invite_seq),
            "email": payload["email"],
            "role": payload.get("role", "employee"),
            "status": "pending",
            "created_at": timezone.now().isoformat().replace("+00:00", "Z"),
        }
        COMPANY_INVITES.insert(0, invite)
        return Response(invite, status=status.HTTP_201_CREATED)


class CompanyAdminUserRoleUpdateView(APIView):
    permission_classes = [IsCompanyAdminOrSuperAdmin]

    @extend_schema(
        operation_id="companyAdminUserRoleUpdate",
        request=UpdateCompanyUserRoleRequestSerializer,
        responses={200: CompanyUserSummarySerializer, 404: ErrorDetailSerializer},
    )
    def patch(self, request, user_id: int):
        role = (request.data.get("role") or "").strip()
        allowed_roles = ["employee", "manager", "company_admin"]
        if role not in allowed_roles:
            raise ValidationError({"detail": _invalid_enum_detail("role", allowed_roles)})
        for user in COMPANY_USERS:
            if user["id"] == user_id:
                user["role"] = role
                return Response(user)
        raise NotFound(detail="User not found.")


class CompanyAdminInviteRevokeView(APIView):
    permission_classes = [IsCompanyAdminOrSuperAdmin]

    @extend_schema(
        operation_id="companyAdminInviteRevoke",
        request=None,
        responses={200: CompanyInviteSerializer, 404: ErrorDetailSerializer},
    )
    def post(self, request, invite_id: int):
        for invite in COMPANY_INVITES:
            if invite["id"] == invite_id:
                invite["status"] = "revoked"
                return Response(invite)
        raise NotFound(detail="Invite not found.")


class PlatformOverviewView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        operation_id="superAdminOverview",
        responses=SuperAdminOverviewSerializer,
    )
    def get(self, request):
        return Response(
            {
                "tenants_count": len(PLATFORM_TENANTS),
                "platform_users_count": len(PLATFORM_USERS),
                "invites_pending": len([x for x in PLATFORM_INVITES if x["status"] == "pending"]),
            }
        )


class PlatformTenantsView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        operation_id="superAdminTenantsList",
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR),
            OpenApiParameter("status", OpenApiTypes.STR),
        ],
        responses=TenantListResponseSerializer,
    )
    def get(self, request):
        q = request.query_params.get("q")
        status_param = _validate_query_enum(
            request.query_params.get("status"), "status", ["active", "trial", "suspended"]
        )
        tenants = PLATFORM_TENANTS
        if q:
            tenants = [t for t in tenants if _contains(t["name"], q)]
        if status_param:
            tenants = [t for t in tenants if t["status"] == status_param]
        return Response({"count": len(tenants), "results": tenants})

    @extend_schema(
        operation_id="superAdminTenantsCreate",
        request=CreateTenantRequestSerializer,
        responses={201: TenantSummarySerializer, 400: ErrorDetailSerializer},
    )
    def post(self, request):
        name = (request.data.get("name") or "").strip()
        if not name:
            raise ValidationError({"detail": "name is required."})
        tenant = {"id": next(_tenant_seq), "name": name, "status": "trial"}
        PLATFORM_TENANTS.insert(0, tenant)
        return Response(tenant, status=status.HTTP_201_CREATED)


class PlatformTenantStatusView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        operation_id="superAdminTenantStatusUpdate",
        request=UpdateTenantStatusRequestSerializer,
        responses={200: TenantSummarySerializer, 404: ErrorDetailSerializer},
    )
    def patch(self, request, tenant_id: int):
        status_param = (request.data.get("status") or "").strip()
        allowed_statuses = ["active", "trial", "suspended"]
        if status_param not in allowed_statuses:
            raise ValidationError(
                {"detail": _invalid_enum_detail("status", allowed_statuses)}
            )
        for tenant in PLATFORM_TENANTS:
            if tenant["id"] == tenant_id:
                tenant["status"] = status_param
                return Response(tenant)
        raise NotFound(detail="Tenant not found.")


class PlatformUsersView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        operation_id="superAdminUsersList",
        responses=PlatformUserListResponseSerializer,
    )
    def get(self, request):
        return Response({"count": len(PLATFORM_USERS), "results": PLATFORM_USERS})


class PlatformInvitesView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        operation_id="superAdminInvitesList",
        responses=PlatformInviteListResponseSerializer,
    )
    def get(self, request):
        return Response({"count": len(PLATFORM_INVITES), "results": PLATFORM_INVITES})

    @extend_schema(
        operation_id="superAdminInvitesCreate",
        request=CreatePlatformInviteRequestSerializer,
        responses={201: PlatformInviteSerializer, 400: ErrorDetailSerializer},
    )
    def post(self, request):
        serializer = CreatePlatformInviteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        invite = {
            "id": next(_platform_invite_seq),
            "email": payload["email"],
            "role": payload.get("role", "support"),
            "status": "pending",
            "created_at": timezone.now().isoformat().replace("+00:00", "Z"),
        }
        PLATFORM_INVITES.insert(0, invite)
        return Response(invite, status=status.HTTP_201_CREATED)


class PlatformInviteRevokeView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        operation_id="superAdminInviteRevoke",
        request=None,
        responses={200: PlatformInviteSerializer, 404: ErrorDetailSerializer},
    )
    def post(self, request, invite_id: int):
        for invite in PLATFORM_INVITES:
            if invite["id"] == invite_id:
                invite["status"] = "revoked"
                return Response(invite)
        raise NotFound(detail="Invite not found.")


class PlatformAuditStatsView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        operation_id="platformAuditStats",
        responses=PlatformAuditStatsSerializer,
    )
    def get(self, request):
        total = len(AUDIT_EVENTS)
        failed = len([x for x in AUDIT_EVENTS if x["status"] == "failed"])
        critical = len([x for x in AUDIT_EVENTS if x["severity"] == "critical"])
        return Response(
            {
                "total_events": total,
                "failed_events": failed,
                "critical_events": critical,
            }
        )


class PlatformAuditEventsView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        operation_id="platformAuditEventsList",
        description=CURSOR_MODE_DESCRIPTION,
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR),
            OpenApiParameter("tenant_id", OpenApiTypes.INT),
            OpenApiParameter("action", OpenApiTypes.STR),
            OpenApiParameter("severity", OpenApiTypes.STR),
            OpenApiParameter("status", OpenApiTypes.STR),
            OpenApiParameter("from", OpenApiTypes.DATETIME),
            OpenApiParameter("to", OpenApiTypes.DATETIME),
            OpenApiParameter("cursor", OpenApiTypes.STR, description=CURSOR_PARAM_DESCRIPTION),
            OpenApiParameter("page", OpenApiTypes.INT),
            OpenApiParameter("page_size", OpenApiTypes.INT),
        ],
        examples=[
            OpenApiExample(
                "Cursor Request Example",
                summary="First cursor page",
                value={
                    "request": "/api/admin/platform/audit/events?cursor=&page_size=2",
                    "response": {
                        "count": 3,
                        "results": [
                            {
                                "id": 3,
                                "timestamp": "2026-04-15T10:20:00Z",
                                "tenant_id": 201,
                                "action": "tenant_status_change",
                                "severity": "high",
                                "status": "success",
                                "actor_type": "system",
                                "message": "Tenant moved to active",
                            }
                        ],
                        "page": 1,
                        "page_size": 2,
                        "next_cursor": "2026-04-15T09:20:00Z::2",
                    },
                },
                response_only=True,
            ),
            OpenApiExample(
                "Cursor Next Page Example",
                summary="Second cursor page",
                value={
                    "request": "/api/admin/platform/audit/events?cursor=2026-04-15T09:20:00Z::2&page_size=2",
                    "response": {
                        "count": 3,
                        "results": [
                            {
                                "id": 1,
                                "timestamp": "2026-04-15T09:00:00Z",
                                "tenant_id": 201,
                                "action": "invite_create",
                                "severity": "medium",
                                "status": "success",
                                "actor_type": "user",
                                "message": "Invite sent to admin@tenant-a.com",
                            }
                        ],
                        "page": 1,
                        "page_size": 2,
                        "next_cursor": None,
                    },
                },
                response_only=True,
            ),
            OpenApiExample(
                "Cursor Validation Error",
                summary="Invalid cursor format",
                value={"detail": "Invalid cursor. Expected format: YYYY-MM-DDTHH:MM:SSZ::<event_id>."},
                response_only=True,
                status_codes=["400"],
            ),
        ],
        responses=PlatformAuditListResponseSerializer,
    )
    def get(self, request):
        events = _apply_audit_filters(request.query_params, AUDIT_EVENTS)
        cursor = request.query_params.get("cursor")
        if cursor is not None:
            results, page_size, next_cursor = _cursor_paginate_events(
                events, request.query_params
            )
            return Response(
                {
                    "count": len(events),
                    "results": results,
                    "page": 1,
                    "page_size": page_size,
                    "next_cursor": next_cursor,
                }
            )
        page = _to_int(request.query_params.get("page", "1"), "page")
        page_size = _to_int(request.query_params.get("page_size", "20"), "page_size")
        if page < 1 or page_size < 1:
            raise ValidationError({"detail": "page and page_size must be positive integers."})
        start = (page - 1) * page_size
        end = start + page_size
        return Response(
            {
                "count": len(events),
                "results": events[start:end],
                "page": page,
                "page_size": page_size,
                "next_cursor": None,
            }
        )


class PlatformAuditExportView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        operation_id="platformAuditExport",
        responses={
            200: OpenApiResponse(
                description='CSV export. Content-Disposition: attachment; filename="platform-audit-YYYY-MM-DD.csv"'
            )
        },
    )
    def get(self, request):
        events = _apply_audit_filters(request.query_params, AUDIT_EVENTS)
        header = "id,timestamp,tenant_id,action,severity,status,actor_type,message"
        rows = [
            ",".join(
                [
                    str(item["id"]),
                    item["timestamp"],
                    str(item["tenant_id"]),
                    item["action"],
                    item["severity"],
                    item["status"],
                    item["actor_type"],
                    item["message"].replace(",", ";"),
                ]
            )
            for item in events
        ]
        csv_text = header + "\n" + "\n".join(rows)
        today = timezone.now().date().isoformat()
        response = HttpResponse(csv_text, content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="platform-audit-{today}.csv"'
        return response


class AdminActionStatsView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        operation_id="adminActionStats",
        responses=AdminActionStatsSerializer,
    )
    def get(self, request):
        total = len(ADMIN_ACTION_EVENTS)
        failed = len([x for x in ADMIN_ACTION_EVENTS if x["status"] == "failed"])
        critical = len([x for x in ADMIN_ACTION_EVENTS if x["severity"] == "critical"])
        return Response(
            {
                "total_events": total,
                "failed_events": failed,
                "critical_events": critical,
            }
        )


class AdminActionEventsView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        operation_id="adminActionEventsList",
        description=CURSOR_MODE_DESCRIPTION,
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR),
            OpenApiParameter("scope", OpenApiTypes.STR),
            OpenApiParameter("severity", OpenApiTypes.STR),
            OpenApiParameter("status", OpenApiTypes.STR),
            OpenApiParameter("action", OpenApiTypes.STR),
            OpenApiParameter("actor", OpenApiTypes.STR),
            OpenApiParameter("from", OpenApiTypes.DATETIME),
            OpenApiParameter("to", OpenApiTypes.DATETIME),
            OpenApiParameter("cursor", OpenApiTypes.STR, description=CURSOR_PARAM_DESCRIPTION),
            OpenApiParameter("page", OpenApiTypes.INT),
            OpenApiParameter("page_size", OpenApiTypes.INT),
        ],
        examples=[
            OpenApiExample(
                "Cursor Request Example",
                summary="First cursor page",
                value={
                    "request": "/api/admin/actions/events?cursor=&page_size=2",
                    "response": {
                        "count": 3,
                        "results": [
                            {
                                "id": 103,
                                "timestamp": "2026-04-15T10:20:00Z",
                                "scope": "platform",
                                "severity": "critical",
                                "status": "failed",
                                "action": "invite_revoke",
                                "actor": "security@platform.com",
                                "details": {"invite_id": 2001},
                            }
                        ],
                        "page": 1,
                        "page_size": 2,
                        "next_cursor": "2026-04-15T10:10:00Z::102",
                    },
                },
                response_only=True,
            ),
            OpenApiExample(
                "Cursor Next Page Example",
                summary="Second cursor page",
                value={
                    "request": "/api/admin/actions/events?cursor=2026-04-15T10:10:00Z::102&page_size=2",
                    "response": {
                        "count": 3,
                        "results": [
                            {
                                "id": 101,
                                "timestamp": "2026-04-15T10:00:00Z",
                                "scope": "company",
                                "severity": "medium",
                                "status": "success",
                                "action": "user_role_update",
                                "actor": "admin@company.com",
                                "details": {"target_user_id": 13},
                            }
                        ],
                        "page": 1,
                        "page_size": 2,
                        "next_cursor": None,
                    },
                },
                response_only=True,
            ),
            OpenApiExample(
                "Cursor Validation Error",
                summary="Invalid cursor format",
                value={"detail": "Invalid cursor. Expected format: YYYY-MM-DDTHH:MM:SSZ::<event_id>."},
                response_only=True,
                status_codes=["400"],
            ),
        ],
        responses=AdminActionListResponseSerializer,
    )
    def get(self, request):
        events = _apply_admin_action_filters(request.query_params, ADMIN_ACTION_EVENTS)
        cursor = request.query_params.get("cursor")
        if cursor is not None:
            results, page_size, next_cursor = _cursor_paginate_events(
                events, request.query_params
            )
            return Response(
                {
                    "count": len(events),
                    "results": results,
                    "page": 1,
                    "page_size": page_size,
                    "next_cursor": next_cursor,
                }
            )
        page = _to_int(request.query_params.get("page", "1"), "page")
        page_size = _to_int(request.query_params.get("page_size", "20"), "page_size")
        if page < 1 or page_size < 1:
            raise ValidationError({"detail": "page and page_size must be positive integers."})
        start = (page - 1) * page_size
        end = start + page_size
        return Response(
            {
                "count": len(events),
                "results": events[start:end],
                "page": page,
                "page_size": page_size,
                "next_cursor": None,
            }
        )


class AdminActionDetailView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        operation_id="adminActionDetail",
        responses={200: AdminActionEventSerializer, 404: ErrorDetailSerializer},
    )
    def get(self, request, action_id: int):
        for event in ADMIN_ACTION_EVENTS:
            if event["id"] == action_id:
                return Response(event)
        raise NotFound(detail="Action event not found.")


class TasksView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="tasksList",
        description=CURSOR_MODE_DESCRIPTION,
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR),
            OpenApiParameter("status", OpenApiTypes.STR),
            OpenApiParameter("priority", OpenApiTypes.STR),
            OpenApiParameter("project_id", OpenApiTypes.INT),
            OpenApiParameter("assignee_id", OpenApiTypes.INT),
            OpenApiParameter("department_id", OpenApiTypes.INT),
            OpenApiParameter("updated_at_from", OpenApiTypes.DATETIME),
            OpenApiParameter("updated_at_to", OpenApiTypes.DATETIME),
            OpenApiParameter("sort", OpenApiTypes.STR),
            OpenApiParameter("cursor", OpenApiTypes.STR, description=CURSOR_PARAM_DESCRIPTION),
            OpenApiParameter("page", OpenApiTypes.INT),
            OpenApiParameter("page_size", OpenApiTypes.INT),
        ],
        examples=[
            OpenApiExample(
                "Cursor Request Example",
                summary="First cursor page",
                value={
                    "request": "/api/tasks?cursor=&page_size=2",
                    "response": {
                        "count": 5,
                        "page": 1,
                        "page_size": 2,
                        "num_pages": 1,
                        "next_cursor": "2026-04-15T12:21:49.573218Z::2004",
                        "results": [
                            {
                                "id": 2005,
                                "title": "Cursor smoke 0",
                                "description": "",
                                "status": "todo",
                                "priority": "medium",
                                "project_id": None,
                                "assignee_id": 12,
                                "department_id": None,
                                "due_date": None,
                                "created_at": "2026-04-15T12:21:49.573218Z",
                                "updated_at": "2026-04-15T12:21:49.573218Z",
                            }
                        ],
                    },
                },
                response_only=True,
            ),
            OpenApiExample(
                "Cursor Next Page Example",
                summary="Second cursor page",
                value={
                    "request": "/api/tasks?cursor=2026-04-15T12:21:49.573218Z::2004&page_size=2",
                    "response": {
                        "count": 5,
                        "page": 1,
                        "page_size": 2,
                        "num_pages": 1,
                        "next_cursor": "2026-04-15T10:00:00Z::2002",
                        "results": [
                            {
                                "id": 2004,
                                "title": "Cursor smoke 1",
                                "description": "",
                                "status": "todo",
                                "priority": "medium",
                                "project_id": None,
                                "assignee_id": 12,
                                "department_id": None,
                                "due_date": None,
                                "created_at": "2026-04-15T12:21:49.573218Z",
                                "updated_at": "2026-04-15T12:21:49.573218Z",
                            }
                        ],
                    },
                },
                response_only=True,
            ),
            OpenApiExample(
                "Cursor Validation Error",
                summary="Invalid cursor format",
                value={"detail": "Invalid cursor. Expected format: YYYY-MM-DDTHH:MM:SSZ::<task_id>."},
                response_only=True,
                status_codes=["400"],
            ),
        ],
        responses=TaskListResponseSerializer,
    )
    def get(self, request):
        tasks = _apply_task_filters(request.query_params, TASK_ITEMS)
        cursor = request.query_params.get("cursor")
        if cursor is not None:
            results, page_size, next_cursor = _cursor_paginate_tasks(tasks, request.query_params)
            return Response(
                {
                    "count": len(tasks),
                    "page": 1,
                    "page_size": page_size,
                    "num_pages": 1,
                    "next_cursor": next_cursor,
                    "results": results,
                }
            )

        sort_param = request.query_params.get("sort", "-updated_at")
        tasks = _sort_tasks(tasks, sort_param)
        results, page, page_size, count, num_pages = _paginate_items(tasks, request.query_params)
        return Response(
            {
                "count": count,
                "page": page,
                "page_size": page_size,
                "num_pages": num_pages,
                "next_cursor": None,
                "results": results,
            }
        )

    @extend_schema(
        operation_id="tasksCreate",
        request=CreateTaskRequestSerializer,
        responses={201: TaskSerializer, 400: ErrorDetailSerializer},
    )
    def post(self, request):
        serializer = CreateTaskRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        now = timezone.now().isoformat().replace("+00:00", "Z")
        due_date = payload.get("due_date")
        task = {
            "id": next(_task_seq),
            "title": payload["title"],
            "description": payload.get("description", ""),
            "status": payload.get("status", "todo"),
            "priority": payload.get("priority", "medium"),
            "project_id": payload.get("project_id"),
            "assignee_id": payload["assignee_id"],
            "department_id": payload.get("department_id"),
            "due_date": due_date.isoformat().replace("+00:00", "Z") if due_date else None,
            "created_at": now,
            "updated_at": now,
        }
        _validate_task_relations(task)
        TASK_ITEMS.insert(0, task)
        _add_task_activity(
            task_id=task["id"],
            event_type="created",
            request=request,
            payload={
                "status": task["status"],
                "priority": task["priority"],
                "assignee_id": task["assignee_id"],
            },
        )
        return Response(task, status=status.HTTP_201_CREATED)


class TaskDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="taskDetail",
        responses={200: TaskSerializer, 404: ErrorDetailSerializer},
    )
    def get(self, request, task_id: int):
        task = _find_task(task_id)
        if not task:
            raise NotFound(detail="Task not found.")
        return Response(task)

    @extend_schema(
        operation_id="taskUpdate",
        request=UpdateTaskRequestSerializer,
        responses={200: TaskSerializer, 404: ErrorDetailSerializer},
    )
    def patch(self, request, task_id: int):
        task = _find_task(task_id)
        if not task:
            raise NotFound(detail="Task not found.")

        serializer = UpdateTaskRequestSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        previous = dict(task)

        for key in [
            "title",
            "description",
            "status",
            "priority",
            "project_id",
            "assignee_id",
            "department_id",
        ]:
            if key in payload:
                task[key] = payload[key]

        if "due_date" in payload:
            due_date = payload["due_date"]
            task["due_date"] = due_date.isoformat().replace("+00:00", "Z") if due_date else None

        _validate_task_relations(task)
        task["updated_at"] = timezone.now().isoformat().replace("+00:00", "Z")
        changed_fields = {}
        for field in [
            "title",
            "description",
            "status",
            "priority",
            "project_id",
            "assignee_id",
            "department_id",
            "due_date",
        ]:
            if previous.get(field) != task.get(field):
                changed_fields[field] = {"from": previous.get(field), "to": task.get(field)}
        _add_task_activity(
            task_id=task["id"],
            event_type="updated",
            request=request,
            payload={"changed_fields": changed_fields},
        )
        return Response(task)

    @extend_schema(
        operation_id="taskDelete",
        responses={204: OpenApiResponse(description="Task deleted"), 404: ErrorDetailSerializer},
    )
    def delete(self, request, task_id: int):
        task = _find_task(task_id)
        if not task:
            raise NotFound(detail="Task not found.")
        _add_task_activity(
            task_id=task["id"],
            event_type="deleted",
            request=request,
            payload={"title": task["title"]},
        )
        TASK_ITEMS.remove(task)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TasksStatsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="tasksStats",
        responses=TaskStatsSerializer,
    )
    def get(self, request):
        total = len(TASK_ITEMS)
        todo = len([t for t in TASK_ITEMS if t["status"] == "todo"])
        in_progress = len([t for t in TASK_ITEMS if t["status"] == "in_progress"])
        done = len([t for t in TASK_ITEMS if t["status"] == "done"])
        high_priority = len([t for t in TASK_ITEMS if t["priority"] == "high"])
        medium_priority = len([t for t in TASK_ITEMS if t["priority"] == "medium"])
        low_priority = len([t for t in TASK_ITEMS if t["priority"] == "low"])
        return Response(
            {
                "total": total,
                "todo": todo,
                "in_progress": in_progress,
                "done": done,
                "high_priority": high_priority,
                "medium_priority": medium_priority,
                "low_priority": low_priority,
            }
        )


class TasksBoardView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="tasksBoard",
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR),
            OpenApiParameter("priority", OpenApiTypes.STR),
            OpenApiParameter("project_id", OpenApiTypes.INT),
            OpenApiParameter("assignee_id", OpenApiTypes.INT),
            OpenApiParameter("department_id", OpenApiTypes.INT),
            OpenApiParameter("updated_at_from", OpenApiTypes.DATETIME),
            OpenApiParameter("updated_at_to", OpenApiTypes.DATETIME),
        ],
        responses=TaskBoardResponseSerializer,
    )
    def get(self, request):
        tasks = _apply_task_filters(request.query_params, TASK_ITEMS)
        return Response(
            {
                "todo": [t for t in tasks if t["status"] == "todo"],
                "in_progress": [t for t in tasks if t["status"] == "in_progress"],
                "done": [t for t in tasks if t["status"] == "done"],
            }
        )


class TasksBulkStatusView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="tasksBulkStatusUpdate",
        request=BulkTaskStatusRequestSerializer,
        responses={200: BulkTaskUpdateResponseSerializer, 400: ErrorDetailSerializer},
    )
    def patch(self, request):
        serializer = BulkTaskStatusRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        task_ids = payload["task_ids"]
        target_status = payload["status"]

        updated_tasks = []
        not_found_ids = []
        now = timezone.now().isoformat().replace("+00:00", "Z")
        for task_id in task_ids:
            task = _find_task(task_id)
            if not task:
                not_found_ids.append(task_id)
                continue
            prev_status = task["status"]
            task["status"] = target_status
            task["updated_at"] = now
            updated_tasks.append(task)
            _add_task_activity(
                task_id=task["id"],
                event_type="bulk_status",
                request=request,
                payload={"from": prev_status, "to": target_status},
            )

        return Response(
            {
                "updated": len(updated_tasks),
                "not_found_ids": not_found_ids,
                "results": updated_tasks,
            }
        )


class TasksBulkAssignView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="tasksBulkAssign",
        request=BulkTaskAssignRequestSerializer,
        responses={200: BulkTaskUpdateResponseSerializer, 400: ErrorDetailSerializer},
    )
    def patch(self, request):
        serializer = BulkTaskAssignRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        task_ids = payload["task_ids"]
        assignee_id = payload["assignee_id"]
        if assignee_id not in _company_user_department_map():
            raise ValidationError({"assignee_id": "Unknown assignee_id."})

        updated_tasks = []
        not_found_ids = []
        now = timezone.now().isoformat().replace("+00:00", "Z")
        for task_id in task_ids:
            task = _find_task(task_id)
            if not task:
                not_found_ids.append(task_id)
                continue
            prev_assignee = task["assignee_id"]
            task["assignee_id"] = assignee_id
            task["updated_at"] = now
            updated_tasks.append(task)
            _add_task_activity(
                task_id=task["id"],
                event_type="bulk_assign",
                request=request,
                payload={"from": prev_assignee, "to": assignee_id},
            )

        return Response(
            {
                "updated": len(updated_tasks),
                "not_found_ids": not_found_ids,
                "results": updated_tasks,
            }
        )


class TaskActivityView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="taskActivityList",
        description=CURSOR_MODE_DESCRIPTION,
        parameters=[
            OpenApiParameter("sort", OpenApiTypes.STR),
            OpenApiParameter("cursor", OpenApiTypes.STR, description=CURSOR_PARAM_DESCRIPTION),
            OpenApiParameter("page", OpenApiTypes.INT),
            OpenApiParameter("page_size", OpenApiTypes.INT),
        ],
        examples=[
            OpenApiExample(
                "Cursor Request Example",
                summary="First cursor page",
                value={
                    "request": "/api/tasks/2003/activity?cursor=&page_size=2",
                    "response": {
                        "count": 3,
                        "page": 1,
                        "page_size": 2,
                        "num_pages": 1,
                        "next_cursor": "2026-04-15T12:23:54.103397Z::2",
                        "results": [
                            {
                                "id": 3,
                                "task_id": 2003,
                                "event_type": "updated",
                                "actor_id": 1,
                                "actor_username": "company_admin_test",
                                "payload": {"changed_fields": {"status": {"from": "todo", "to": "in_progress"}}},
                                "created_at": "2026-04-15T12:23:54.103397Z",
                            }
                        ],
                    },
                },
                response_only=True,
            ),
            OpenApiExample(
                "Cursor Next Page Example",
                summary="Second cursor page",
                value={
                    "request": "/api/tasks/2003/activity?cursor=2026-04-15T12:23:54.103397Z::2&page_size=2",
                    "response": {
                        "count": 3,
                        "page": 1,
                        "page_size": 2,
                        "num_pages": 1,
                        "next_cursor": None,
                        "results": [
                            {
                                "id": 1,
                                "task_id": 2003,
                                "event_type": "created",
                                "actor_id": 1,
                                "actor_username": "company_admin_test",
                                "payload": {"status": "todo", "priority": "medium", "assignee_id": 12},
                                "created_at": "2026-04-15T12:23:54.100000Z",
                            }
                        ],
                    },
                },
                response_only=True,
            ),
            OpenApiExample(
                "Cursor Validation Error",
                summary="Invalid cursor format",
                value={"detail": "Invalid cursor. Expected format: YYYY-MM-DDTHH:MM:SSZ::<event_id>."},
                response_only=True,
                status_codes=["400"],
            ),
        ],
        responses={200: TaskActivityListResponseSerializer, 404: ErrorDetailSerializer},
    )
    def get(self, request, task_id: int):
        task = _find_task(task_id)
        if not task:
            raise NotFound(detail="Task not found.")
        events = _task_activity_for(task_id)
        cursor = request.query_params.get("cursor")
        if cursor is not None:
            results, page_size, next_cursor = _cursor_paginate_activity(
                events, request.query_params
            )
            return Response(
                {
                    "count": len(events),
                    "page": 1,
                    "page_size": page_size,
                    "num_pages": 1,
                    "next_cursor": next_cursor,
                    "results": results,
                }
            )

        sort_param = request.query_params.get("sort", "-created_at")
        if sort_param not in {"created_at", "-created_at"}:
            raise ValidationError(
                {"detail": "Invalid sort. Allowed: created_at, -created_at."}
            )
        reverse = sort_param.startswith("-")
        events = sorted(events, key=lambda x: x["created_at"], reverse=reverse)
        results, page, page_size, count, num_pages = _paginate_items(events, request.query_params)
        return Response(
            {
                "count": count,
                "page": page,
                "page_size": page_size,
                "num_pages": num_pages,
                "next_cursor": None,
                "results": results,
            }
        )
