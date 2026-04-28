from copy import deepcopy
from datetime import datetime, timezone
from itertools import count
import re
from rest_framework.exceptions import NotFound, ValidationError

# Same-origin paths: served by Vite `public/` (SPA host), avoids dead `cdn.atom.ai` in local dev.
_AVATAR_EMP_1 = "/avatars/emp-1.svg"
_AVATAR_EMP_2 = "/avatars/emp-2.svg"
_AVATAR_EMP_3 = "/avatars/emp-3.svg"
_LOGO_BCS_DRIFT = "/avatars/building-bcs-drift.svg"

BUILDINGS = [
    {
        "id": "bcs-drift",
        "name": "BCS Drift",
        "status": "green",
        "floors": 9,
        "employees": 124,
        "online_now": 71,
        "risky_tasks": 8,
        "overdue_tasks": 3,
        "color": "#0EA5E9",
        "height_ratio": 0.72,
        "latest_event": "Q2 board prep",
        "logo": _LOGO_BCS_DRIFT,
    }
]

DEPARTMENTS = {
    "bcs-drift": [
        {
            "id": "marketing",
            "floor": 3,
            "name": "Marketing",
            "status": "yellow",
            "employee_count": 14,
            "online_count": 10,
            "risky_tasks": 2,
            "overdue_tasks": 1,
            "lead": "Alex K",
        }
    ]
}

FLOOR_WORKSPACES = {
    ("bcs-drift", "3"): {
        "building_name": "BCS Drift",
        "department": "Marketing",
        "zones": [
            {
                "x": 10,
                "y": 10,
                "w": 220,
                "h": 130,
                "label": "Meeting Zone",
                "color": "rgba(255,255,255,0.05)",
                "stroke_color": "rgba(255,255,255,0.15)",
            }
        ],
        "employees": [
            {
                "id": "emp-1",
                "full_name": "Alex Kim",
                "role": "Marketing Lead",
                "avatar": _AVATAR_EMP_1,
                "status": "online",
                "email": "alex@example.com",
                "telegram": "@alex",
                "timezone": "UTC+3",
                "hours": "10:00-19:00",
                "x": 120,
                "y": 90,
                "points": 210,
                "next_goal": 260,
                "next_goal_label": "Q2 performance",
                "tasks": [
                    {
                        "id": "task-1",
                        "title": "KPI report",
                        "column": "in_progress",
                        "priority": "high",
                        "due": "2026-04-20T00:00:00Z",
                    }
                ],
            }
        ],
    }
}

EMPLOYEE_CONTEXT = {
    ("bcs-drift", "3", "emp-1"): {
        "my_tasks": [
            {
                "id": "task-1",
                "title": "KPI report",
                "column": "in_progress",
                "priority": "high",
                "due": "2026-04-20T00:00:00Z",
            }
        ],
        "documents": [
            {
                "id": "doc-1",
                "title": "Marketing roadmap Q2",
                "type": "doc",
                "updated_at": "2026-04-14T07:42:00Z",
                "owner": "Alex K",
                "href": "",
            }
        ],
        "activity_feed": [
            {
                "id": "act-1",
                "type": "task",
                "title": "Task updated",
                "timestamp": "2026-04-14T08:10:00Z",
            }
        ],
        "project_context": [
            {
                "id": "pr-1",
                "name": "Growth Sprint",
                "status": "on_track",
                "summary": "Conversion growing",
            }
        ],
    }
}

EMPLOYEE_PROFILE_EXTRA = {
    ("bcs-drift", "3", "emp-1"): {
        "projects": [
            {
                "id": "pr-1",
                "name": "Growth Sprint",
                "status": "on_track",
                "summary": "Conversion growing",
            }
        ],
        "activity_feed": [
            {
                "id": "act-1",
                "type": "task",
                "title": "Task updated",
                "timestamp": "2026-04-14T08:10:00Z",
            }
        ],
        "comments_history": [
            {
                "id": "cmt-1",
                "author": "Alex K",
                "text": "Need KPI update",
                "created_at": "2026-04-14T07:10:00Z",
            }
        ],
        "performance": {
            "completed_tasks": 12,
            "total_tasks": 18,
            "on_time_rate": 67,
            "response_rate": 92,
        },
    }
}

EMPLOYEE_VERTICAL_DIRECTORY = {
    "emp-1": {
        "header": {
            "id": "emp-1",
            "full_name": "Alex Kim",
            "role": "employee",
            "title": "Marketing Lead",
            "avatar": _AVATAR_EMP_1,
            "department": "Marketing",
            "status": "online",
            "presence_status": "online",
            "work_status": "on_track",
        },
        "contacts": {
            "work_email": "alex@company.com",
            "telegram": "@alex",
            "personal_email": "alex.personal@gmail.com",
            "phone": "+79990000001",
            "city": "Moscow",
            "working_hours": "10:00 - 19:00",
            "timezone": "Europe/Moscow",
            "is_work_email_public": True,
        },
        "performance": {
            "completed_tasks": 12,
            "total_tasks": 18,
            "on_time_rate": 67,
            "response_rate": 92,
        },
        "projects": [
            {"id": "pr-1", "name": "Growth Sprint", "status": "on_track", "summary": "Conversion growing"}
        ],
        "achievements": [{"id": "ach-1", "title": "Top contributor", "period": "Q1"}],
        "bonus_goals": [{"id": "bg-1", "title": "Q2 performance", "progress": 81}],
        "activity_feed": [
            {
                "id": "a1",
                "type": "task",
                "title": "Обновлена задача",
                "timestamp": "2026-04-17T10:00:00Z",
                "href": "/app/tasks/t1",
                "actor": {"id": "emp-2", "name": "Maria Smirnova"},
            }
        ],
        "comments_history": [{"id": "cm-1", "author": "Maria Smirnova", "text": "Круто движется!", "created_at": "2026-04-17T09:00:00Z"}],
        "preferences": {
            "email_digest": "daily",
            "task_reminders": True,
            "mentions_push": True,
            "ai_suggestions": True,
        },
        "editable_fields": [
            "personal_email",
            "phone",
            "telegram",
            "city",
            "working_hours",
            "timezone",
            "preferences",
            "presence_status",
            "work_status",
        ],
    },
    "emp-2": {
        "header": {
            "id": "emp-2",
            "full_name": "Maria Smirnova",
            "role": "manager",
            "title": "Marketing Manager",
            "avatar": _AVATAR_EMP_2,
            "department": "Marketing",
            "status": "online",
            "presence_status": "online",
            "work_status": "on_track",
        },
        "contacts": {
            "work_email": "maria@company.com",
            "telegram": "@maria",
            "personal_email": "maria.personal@gmail.com",
            "phone": "+79990000002",
            "city": "Moscow",
            "working_hours": "10:00 - 19:00",
            "timezone": "Europe/Moscow",
            "is_work_email_public": True,
        },
        "performance": {"completed_tasks": 20, "total_tasks": 24, "on_time_rate": 84, "response_rate": 96},
        "projects": [{"id": "pr-2", "name": "Brand Uplift", "status": "on_track", "summary": "CTR up +12%"}],
        "achievements": [{"id": "ach-2", "title": "Team mentor", "period": "Q1"}],
        "bonus_goals": [{"id": "bg-2", "title": "MQL target", "progress": 74}],
        "activity_feed": [],
        "comments_history": [],
        "preferences": {
            "email_digest": "weekly",
            "task_reminders": True,
            "mentions_push": True,
            "ai_suggestions": False,
        },
        "editable_fields": [
            "personal_email",
            "phone",
            "telegram",
            "city",
            "working_hours",
            "timezone",
            "preferences",
            "presence_status",
            "work_status",
        ],
    },
    "emp-3": {
        "header": {
            "id": "emp-3",
            "full_name": "Company Admin",
            "role": "company_admin",
            "title": "Company Admin",
            "avatar": _AVATAR_EMP_3,
            "department": "Administration",
            "status": "online",
            "presence_status": "online",
            "work_status": "on_track",
        },
        "contacts": {
            "work_email": "company_admin_test@atom.local",
            "telegram": "@company_admin",
            "personal_email": "company_admin@gmail.com",
            "phone": "+79990000003",
            "city": "Moscow",
            "working_hours": "09:00 - 18:00",
            "timezone": "Europe/Moscow",
            "is_work_email_public": False,
        },
        "performance": {"completed_tasks": 31, "total_tasks": 33, "on_time_rate": 91, "response_rate": 98},
        "projects": [{"id": "pr-3", "name": "Ops Control", "status": "on_track", "summary": "Admin SLA stable"}],
        "achievements": [{"id": "ach-3", "title": "Process owner", "period": "Q1"}],
        "bonus_goals": [{"id": "bg-3", "title": "Platform stability", "progress": 88}],
        "activity_feed": [],
        "comments_history": [],
        "preferences": {
            "email_digest": "daily",
            "task_reminders": True,
            "mentions_push": True,
            "ai_suggestions": True,
        },
        "editable_fields": [
            "personal_email",
            "phone",
            "telegram",
            "city",
            "working_hours",
            "timezone",
            "preferences",
            "presence_status",
            "work_status",
        ],
    },
}

USERNAME_TO_EMPLOYEE = {
    "employee_test": "emp-1",
    "manager_test": "emp-2",
    "company_admin_test": "emp-3",
}

EMPLOYEE_VERTICAL_TASKS = {
    "emp-1": {
        "overdue": [
            {"id": "t-over-1", "title": "Finish KPI deck", "column": "todo", "priority": "high", "due": "2026-04-10T00:00:00Z"}
        ],
        "today": [
            {"id": "t-today-1", "title": "Review campaign stats", "column": "in_progress", "priority": "medium", "due": "2026-04-17T00:00:00Z"}
        ],
        "this_week": [
            {"id": "t-week-1", "title": "Prepare roadmap notes", "column": "todo", "priority": "medium", "due": "2026-04-20T00:00:00Z"}
        ],
        "later": [
            {"id": "t-later-1", "title": "Draft Q3 hypotheses", "column": "todo", "priority": "low", "due": "2026-04-29T00:00:00Z"}
        ],
        "done": [
            {"id": "t-done-1", "title": "Publish retro notes", "column": "done", "priority": "low", "due": "2026-04-15T00:00:00Z"}
        ],
    },
    "emp-2": {"overdue": [], "today": [], "this_week": [], "later": [], "done": []},
    "emp-3": {"overdue": [], "today": [], "this_week": [], "later": [], "done": []},
}


def _slug_username(username: str) -> str:
    raw = (username or "").strip().lower()
    if not raw:
        return "user"
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return slug or "user"


def _ensure_dynamic_employee_profile(username: str) -> str:
    mapped = USERNAME_TO_EMPLOYEE.get(username)
    if mapped and mapped in EMPLOYEE_VERTICAL_DIRECTORY:
        return mapped

    slug = _slug_username(username)
    candidate = f"emp-dyn-{slug}"
    employee_id = candidate
    seq = 2
    while employee_id in EMPLOYEE_VERTICAL_DIRECTORY:
        employee_id = f"{candidate}-{seq}"
        seq += 1

    template = deepcopy(EMPLOYEE_VERTICAL_DIRECTORY["emp-1"])
    display_name = (username or "").strip() or "Employee"
    template["header"]["id"] = employee_id
    template["header"]["full_name"] = display_name
    template["header"]["first_name"] = display_name
    template["header"]["last_name"] = ""
    template["header"]["role"] = "employee"
    template["header"]["title"] = "Employee"
    template["header"]["department"] = "Unassigned"

    template["contacts"]["work_email"] = ""
    template["contacts"]["personal_email"] = ""
    template["contacts"]["telegram"] = ""
    template["contacts"]["phone"] = ""
    template["contacts"]["city"] = ""
    template["contacts"]["is_work_email_public"] = False

    EMPLOYEE_VERTICAL_DIRECTORY[employee_id] = template
    EMPLOYEE_VERTICAL_TASKS[employee_id] = {
        "overdue": [],
        "today": [],
        "this_week": [],
        "later": [],
        "done": [],
    }
    USERNAME_TO_EMPLOYEE[username] = employee_id
    return employee_id


def _assignee_fields(employee_id: str) -> dict[str, str]:
    profile = EMPLOYEE_VERTICAL_DIRECTORY.get(employee_id)
    if not profile:
        return {
            "employee_id": employee_id,
            "employee_name": "Unknown",
            "employee_role": "Unknown",
        }
    header = profile["header"]
    display_role = header.get("title") or header.get("role") or "employee"
    return {
        "employee_id": str(header.get("id", employee_id)),
        "employee_name": str(header.get("full_name", "Unknown")),
        "employee_role": str(display_role),
    }


def with_task_assignee(employee_id: str, task: dict) -> dict:
    merged = deepcopy(task)
    merged.update(_assignee_fields(employee_id))
    return merged


_quick_task_seq = count(2000)
_task_meta_seq = count(1)
_TASK_THREADS: dict[str, dict[str, list]] = {}


def _task_thread_key(employee_id: str, task_id: str) -> str:
    return f"{employee_id}::{task_id}"


def _drop_task_thread(employee_id: str, task_id: str) -> None:
    _TASK_THREADS.pop(_task_thread_key(employee_id, task_id), None)


def _ensure_task_thread(employee_id: str, task_id: str) -> dict[str, list]:
    get_workspace_task(employee_id, task_id)
    key = _task_thread_key(employee_id, task_id)
    if key not in _TASK_THREADS:
        _TASK_THREADS[key] = {"comments": [], "checklist": [], "audit": []}
    return _TASK_THREADS[key]


def append_workspace_task_audit(
    employee_id: str,
    task_id: str,
    action: str,
    actor_name: str,
    actor_role: str = "employee",
    details: str = "",
) -> None:
    thread = _ensure_task_thread(employee_id, task_id)
    event_id = f"a-{next(_task_meta_seq)}"
    thread["audit"].insert(
        0,
        {
            "id": event_id,
            "action": action,
            "actor_name": actor_name,
            "actor_role": actor_role,
            "timestamp": _iso_z_now(),
            "details": details,
        },
    )


def list_workspace_task_audit_events(employee_id: str, task_id: str) -> dict:
    thread = _ensure_task_thread(employee_id, task_id)
    items = deepcopy(thread["audit"])
    return {"results": items, "count": len(items)}


def list_workspace_task_comments(employee_id: str, task_id: str) -> dict:
    thread = _ensure_task_thread(employee_id, task_id)
    items = deepcopy(thread["comments"])
    return {"results": items, "count": len(items)}


def add_workspace_task_comment(employee_id: str, task_id: str, message: str, author_name: str, author_role: str) -> None:
    thread = _ensure_task_thread(employee_id, task_id)
    cid = f"c-{next(_task_meta_seq)}"
    thread["comments"].insert(
        0,
        {
            "id": cid,
            "message": message.strip(),
            "author_name": author_name,
            "author_role": author_role,
            "created_at": _iso_z_now(),
        },
    )


def list_workspace_task_checklist(employee_id: str, task_id: str) -> dict:
    thread = _ensure_task_thread(employee_id, task_id)
    items = deepcopy(thread["checklist"])
    items.sort(key=lambda row: int(row.get("position", 0)))
    return {"results": items, "count": len(items)}


def add_workspace_task_checklist_item(employee_id: str, task_id: str, title: str) -> None:
    thread = _ensure_task_thread(employee_id, task_id)
    positions = [int(x.get("position", 0)) for x in thread["checklist"]]
    next_pos = max(positions, default=0) + 1
    iid = f"cl-{next(_task_meta_seq)}"
    thread["checklist"].append(
        {"id": iid, "title": title.strip(), "done": False, "position": next_pos},
    )


def patch_workspace_task_checklist_item(employee_id: str, task_id: str, item_id: str, payload: dict) -> None:
    thread = _ensure_task_thread(employee_id, task_id)
    for item in thread["checklist"]:
        if str(item.get("id")) != str(item_id):
            continue
        if "title" in payload and payload["title"] is not None:
            item["title"] = str(payload["title"]).strip()
        if "done" in payload and payload["done"] is not None:
            item["done"] = bool(payload["done"])
        if "position" in payload and payload["position"] is not None:
            item["position"] = int(payload["position"])
        return
    raise NotFound(detail="Checklist item not found.")


def delete_workspace_task_checklist_item(employee_id: str, task_id: str, item_id: str) -> None:
    thread = _ensure_task_thread(employee_id, task_id)
    for idx, item in enumerate(list(thread["checklist"])):
        if str(item.get("id")) == str(item_id):
            thread["checklist"].pop(idx)
            return
    raise NotFound(detail="Checklist item not found.")


def _iso_z_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def list_buildings() -> list[dict]:
    return deepcopy(BUILDINGS)


def get_building(building_id: str) -> dict:
    for building in BUILDINGS:
        if building["id"] == building_id:
            return deepcopy(building)
    raise NotFound(detail=f"Building '{building_id}' not found.")


def get_departments(building_id: str) -> list[dict]:
    _ = get_building(building_id)
    return deepcopy(DEPARTMENTS.get(building_id, []))


def get_building_detail(building_id: str) -> dict:
    building = get_building(building_id)
    return {
        "id": building["id"],
        "name": building["name"],
        "departments": get_departments(building_id),
    }


def get_floor_workspace(building_id: str, floor_id: str) -> dict:
    _ = get_building(building_id)
    key = (building_id, str(floor_id))
    if key not in FLOOR_WORKSPACES:
        raise NotFound(detail=f"Workspace for building '{building_id}' floor '{floor_id}' not found.")
    return deepcopy(FLOOR_WORKSPACES[key])


def _get_employee_from_workspace(building_id: str, floor_id: str, employee_id: str) -> dict:
    workspace = get_floor_workspace(building_id, floor_id)
    for employee in workspace["employees"]:
        if employee["id"] == employee_id:
            return deepcopy(employee)
    raise NotFound(detail=f"Employee '{employee_id}' not found in workspace.")


def get_employee_workspace_context(building_id: str, floor_id: str, employee_id: str) -> dict:
    employee = _get_employee_from_workspace(building_id, floor_id, employee_id)
    key = (building_id, str(floor_id), employee_id)
    extra = EMPLOYEE_CONTEXT.get(key, {})
    my_tasks_raw = deepcopy(extra.get("my_tasks", []))
    return {
        "employee": employee,
        "my_tasks": [with_task_assignee(employee_id, t) for t in my_tasks_raw],
        "documents": deepcopy(extra.get("documents", [])),
        "activity_feed": deepcopy(extra.get("activity_feed", [])),
        "project_context": deepcopy(extra.get("project_context", [])),
    }


def get_employee_profile(building_id: str, floor_id: str, employee_id: str) -> dict:
    workspace = get_floor_workspace(building_id, floor_id)
    employee = _get_employee_from_workspace(building_id, floor_id, employee_id)
    key = (building_id, str(floor_id), employee_id)
    extra = EMPLOYEE_PROFILE_EXTRA.get(key, {})
    return {
        "employee": employee,
        "building_name": workspace["building_name"],
        "department": workspace["department"],
        "projects": deepcopy(extra.get("projects", [])),
        "activity_feed": deepcopy(extra.get("activity_feed", [])),
        "comments_history": deepcopy(extra.get("comments_history", [])),
        "performance": deepcopy(
            extra.get(
                "performance",
                {
                    "completed_tasks": 0,
                    "total_tasks": 0,
                    "on_time_rate": 0,
                    "response_rate": 0,
                },
            )
        ),
    }


def resolve_employee_id_for_username(username: str) -> str:
    return _ensure_dynamic_employee_profile(username)


def _role_extras(role_code: str) -> dict | None:
    if role_code == "manager":
        return {"kind": "manager", "team_size": 7, "at_risk_tasks": 1}
    if role_code == "company_admin":
        return {"kind": "admin", "alerts": 2, "pending_invites": 1}
    if role_code in {"executive", "ceo"}:
        return {"kind": "executive", "attention_buildings": 1}
    return None


def _count_workspace_tasks_with_column(employee_id: str, column: str) -> int:
    grouped = EMPLOYEE_VERTICAL_TASKS.get(employee_id)
    if not grouped:
        return 0
    n = 0
    for tasks in grouped.values():
        for task in tasks:
            if str(task.get("column")) == column:
                n += 1
    return n


def _grouped_tasks_payload(employee_id: str) -> list[dict]:
    tasks = EMPLOYEE_VERTICAL_TASKS.get(employee_id, {"overdue": [], "today": [], "this_week": [], "later": [], "done": []})
    labels = {
        "overdue": "Просрочено",
        "today": "Сегодня",
        "this_week": "На этой неделе",
        "later": "Позже",
        "done": "Сделано",
    }
    return [
        {
            "key": key,
            "label": labels[key],
            "tasks": [with_task_assignee(employee_id, t) for t in tasks.get(key, [])],
        }
        for key in ["overdue", "today", "this_week", "later", "done"]
    ]


def get_employee_workspace(request, viewer_role: str) -> dict:
    from apps.projects import project_documents as project_documents_service
    from apps.projects.models import ProjectMember
    from apps.storage.warnings import collect_storage_warnings_for_user, storage_backend_hint

    employee_id = resolve_employee_id_for_username(request.user.username)
    profile = deepcopy(EMPLOYEE_VERTICAL_DIRECTORY.get(employee_id))
    if not profile:
        raise NotFound(detail=f"Employee '{employee_id}' not found.")
    grouped = _grouped_tasks_payload(employee_id)
    overdue_count = len(next(group["tasks"] for group in grouped if group["key"] == "overdue"))
    done_count = len(next(group["tasks"] for group in grouped if group["key"] == "done"))
    result = {
        "employee": {
            "id": profile["header"]["id"],
            "full_name": profile["header"]["full_name"],
            # role is canonical for logic; title is display label.
            "role": profile["header"]["role"],
            "title": profile["header"]["title"],
            "avatar": profile["header"]["avatar"],
            "status": profile["header"]["status"],
            "email": profile["contacts"]["work_email"],
            "telegram": profile["contacts"]["telegram"],
            "timezone": profile["contacts"]["timezone"],
            "hours": profile["contacts"]["working_hours"],
        },
        "greeting": {
            "user_name": profile["header"]["full_name"].split(" ")[0],
            "time_greeting": "Добрый день",
            "focus_message": "Сегодня закрываем employee vertical.",
            "ai_tip": "Сфокусируйся на overdue и today задачах.",
        },
        "today_focus": {
            "date": _iso_z_now(),
            "primary_goal": "Закрыть P0 employee vertical",
            "meetings_count": 2,
            "tasks_due_today": len(next(group["tasks"] for group in grouped if group["key"] == "today")),
            "tasks_overdue": overdue_count,
            "ai_suggestion": "Начни с highest priority overdue задачи.",
        },
        "quick_actions": [
            {"id": "qa-1", "kind": "create_task", "label": "Новая задача", "icon": "plus-square"},
            {"id": "qa-2", "kind": "open_ai", "label": "Спросить AI", "icon": "sparkles"},
            {"id": "qa-3", "kind": "new_note", "label": "Заметка", "icon": "notebook-pen"},
            {
                "id": "qa-4",
                "kind": "open_profile",
                "label": "Мой профиль",
                "description": "Контакты и настройки",
                "icon": "user",
            },
        ],
        "stats": {
            "tasks_in_progress": _count_workspace_tasks_with_column(employee_id, "in_progress"),
            "tasks_done": done_count,
            "tasks_overdue": overdue_count,
            "streak_days": 4,
            "week_balance": {"planned_hours": 40, "logged_hours": 31},
        },
        "tasks_grouped": grouped,
        "documents": project_documents_service.list_project_documents_for_workspace(request),
        "project_context": deepcopy(profile["projects"]),
        "activity_feed": deepcopy(profile["activity_feed"]),
        "ai_context": {
            "employee_id": employee_id,
            "open_task_ids": [task["id"] for group in grouped for task in group["tasks"] if task.get("column") != "done"],
            "suggested_prompts": ["Что в фокусе на сегодня?", "Собери краткий апдейт по задачам."],
        },
        "viewer_role": viewer_role,
        "contract_meta": {
            "encoding": "utf-8",
            "locale": "ru-RU",
            "timestamp_format": "iso-8601-z",
            "header_role_source_of_truth": "header.role",
        },
        "storage_hints": {
            "warnings": collect_storage_warnings_for_user(request.user),
            "backend": storage_backend_hint(),
        },
    }
    invites = (
        ProjectMember.objects.filter(user=request.user, is_active=False)
        .select_related("project", "project__created_by")
        .order_by("-joined_at")[:20]
    )
    result["project_membership_invites"] = [
        {
            "id": m.pk,
            "project_id": str(m.project_id),
            "project_name": m.project.name,
            "role": m.role,
            "invited_by_name": (
                (m.project.created_by.get_full_name() or m.project.created_by.username or "").strip()
                if m.project.created_by
                else ""
            ),
        }
        for m in invites
    ]
    extras = _role_extras(viewer_role)
    if extras:
        result["role_extras"] = extras
    return result


def get_employee_owner_profile(employee_id: str) -> dict:
    profile = deepcopy(EMPLOYEE_VERTICAL_DIRECTORY.get(employee_id))
    if not profile:
        raise NotFound(detail=f"Employee '{employee_id}' not found.")
    return {
        "view": "owner",
        "header": {
            **profile["header"],
            "role_source_of_truth": "role",
        },
        "contacts": {k: v for k, v in profile["contacts"].items() if k != "is_work_email_public"},
        "performance": profile["performance"],
        "projects": profile["projects"],
        "achievements": profile["achievements"],
        "bonus_goals": profile["bonus_goals"],
        "activity_feed": profile["activity_feed"],
        "comments_history": profile["comments_history"],
        "preferences": profile["preferences"],
        "editable_fields": profile["editable_fields"],
    }


def get_employee_public_profile(employee_id: str) -> dict:
    profile = deepcopy(EMPLOYEE_VERTICAL_DIRECTORY.get(employee_id))
    if not profile:
        raise NotFound(detail=f"Employee '{employee_id}' not found.")
    contacts = {"telegram": profile["contacts"].get("telegram")}
    if profile["contacts"].get("is_work_email_public"):
        contacts["work_email"] = profile["contacts"]["work_email"]
    return {
        "view": "public",
        "header": {
            **profile["header"],
            "role_source_of_truth": "role",
        },
        "contacts": contacts,
        "public_projects": profile["projects"],
        "public_achievements": profile["achievements"],
        "public_stats": {
            "completed_tasks": profile["performance"]["completed_tasks"],
            "on_time_rate": profile["performance"]["on_time_rate"],
        },
    }


def patch_employee_owner_profile(employee_id: str, patch: dict) -> dict:
    profile = EMPLOYEE_VERTICAL_DIRECTORY.get(employee_id)
    if not profile:
        raise NotFound(detail=f"Employee '{employee_id}' not found.")

    if "first_name" in patch or "last_name" in patch:
        first_name_raw = patch.get("first_name")
        last_name_raw = patch.get("last_name")
        current_full_name = str(profile["header"].get("full_name") or "").strip()
        current_parts = [p for p in current_full_name.split(" ") if p]
        current_first = current_parts[0] if current_parts else ""
        current_last = " ".join(current_parts[1:]) if len(current_parts) > 1 else ""
        first_name = (
            str(first_name_raw).strip()
            if first_name_raw is not None
            else current_first
        )
        last_name = (
            str(last_name_raw).strip()
            if last_name_raw is not None
            else current_last
        )
        profile["header"]["first_name"] = first_name
        profile["header"]["last_name"] = last_name
        profile["header"]["full_name"] = f"{first_name} {last_name}".strip() or current_full_name

    for key in ["personal_email", "phone", "telegram", "city", "working_hours", "timezone"]:
        if key in patch:
            profile["contacts"][key] = patch[key]
    if "preferences" in patch and isinstance(patch["preferences"], dict):
        profile["preferences"].update(patch["preferences"])
    if "presence_status" in patch:
        v = patch["presence_status"]
        profile["header"]["presence_status"] = v
        profile["header"]["status"] = v
    if "work_status" in patch:
        profile["header"]["work_status"] = patch["work_status"]
    return get_employee_owner_profile(employee_id)


def create_workspace_quick_task(employee_id: str, title: str, slot: str, priority: str | None, project_id: str | None) -> dict:
    if employee_id not in EMPLOYEE_VERTICAL_TASKS:
        raise NotFound(detail=f"Employee '{employee_id}' not found.")
    task_id = f"t-{next(_quick_task_seq)}"
    task = {
        "id": task_id,
        "title": title,
        "column": "todo" if slot != "done" else "done",
        "priority": priority or "medium",
        "due": _iso_z_now(),
    }
    task = {**task, **_assignee_fields(employee_id)}
    if slot not in EMPLOYEE_VERTICAL_TASKS[employee_id]:
        EMPLOYEE_VERTICAL_TASKS[employee_id][slot] = []
    EMPLOYEE_VERTICAL_TASKS[employee_id][slot].insert(0, task)
    if project_id:
        profile = EMPLOYEE_VERTICAL_DIRECTORY.get(employee_id)
        if profile:
            profile["activity_feed"].insert(
                0,
                {
                    "id": f"a-{task_id}",
                    "type": "task",
                    "title": f"Quick task created for project {project_id}",
                    "timestamp": _iso_z_now(),
                    "href": f"/app/tasks/{task_id}",
                    "actor": {"id": employee_id, "name": profile["header"]["full_name"]},
                },
            )
    return {"task_id": task_id, "slot": slot, "title": title}


def _all_employee_tasks(employee_id: str) -> list[dict]:
    grouped = EMPLOYEE_VERTICAL_TASKS.get(employee_id)
    if not grouped:
        raise NotFound(detail=f"Employee '{employee_id}' not found.")
    items: list[dict] = []
    for group_key in ["overdue", "today", "this_week", "later", "done"]:
        for task in grouped.get(group_key, []):
            row = deepcopy(task)
            row["group"] = group_key
            items.append(row)
    return items


def list_workspace_tasks(employee_id: str, filters: dict | None = None) -> list[dict]:
    items = _all_employee_tasks(employee_id)
    params = filters or {}
    q = (params.get("q") or "").strip().lower()
    column = (params.get("column") or params.get("status") or "").strip()
    priority = (params.get("priority") or "").strip()
    if q:
        items = [t for t in items if q in str(t.get("title", "")).lower()]
    if column:
        items = [t for t in items if t.get("column") == column]
    if priority:
        items = [t for t in items if t.get("priority") == priority]
    return [with_task_assignee(employee_id, t) for t in items]


def get_workspace_task(employee_id: str, task_id: str) -> dict:
    for task in _all_employee_tasks(employee_id):
        if str(task.get("id")) == str(task_id):
            return with_task_assignee(employee_id, task)
    raise NotFound(detail="Task not found.")


def create_workspace_task(employee_id: str, payload: dict) -> dict:
    title = (payload.get("title") or "").strip()
    if not title:
        raise ValidationError({"detail": "title is required."})
    column = payload.get("column") or payload.get("status") or "todo"
    if column not in {"todo", "in_progress", "done"}:
        raise ValidationError({"detail": "Invalid column."})
    priority = payload.get("priority") or "medium"
    if priority not in {"high", "medium", "low"}:
        raise ValidationError({"detail": "Invalid priority."})
    due = payload.get("due") or _iso_z_now()
    task_id = f"t-{next(_quick_task_seq)}"
    task = {
        "id": task_id,
        "title": title,
        "column": column,
        "priority": priority,
        "due": due,
        "project_id": payload.get("project_id"),
    }
    # Alias route stores into "today" by default so workspace can render it immediately.
    EMPLOYEE_VERTICAL_TASKS.setdefault(employee_id, {"overdue": [], "today": [], "this_week": [], "later": [], "done": []})
    target_group = "done" if column == "done" else "today"
    EMPLOYEE_VERTICAL_TASKS[employee_id].setdefault(target_group, [])
    merged = {**task, **_assignee_fields(employee_id)}
    EMPLOYEE_VERTICAL_TASKS[employee_id][target_group].insert(0, merged)
    return with_task_assignee(employee_id, merged)


def patch_workspace_task(employee_id: str, task_id: str, payload: dict) -> dict:
    grouped = EMPLOYEE_VERTICAL_TASKS.get(employee_id)
    if not grouped:
        raise NotFound(detail=f"Employee '{employee_id}' not found.")
    for group_name, tasks in grouped.items():
        for task in tasks:
            if str(task.get("id")) != str(task_id):
                continue
            if "title" in payload:
                task["title"] = payload["title"]
            if "column" in payload or "status" in payload:
                new_column = payload.get("column") or payload.get("status")
                if new_column not in {"todo", "in_progress", "done"}:
                    raise ValidationError({"detail": "Invalid column."})
                task["column"] = new_column
            if "priority" in payload:
                new_priority = payload["priority"]
                if new_priority not in {"high", "medium", "low"}:
                    raise ValidationError({"detail": "Invalid priority."})
                task["priority"] = new_priority
            if "due" in payload:
                task["due"] = payload["due"]
            task["updated_at"] = _iso_z_now()
            if group_name != "done" and task.get("column") == "done":
                tasks.remove(task)
                grouped.setdefault("done", [])
                grouped["done"].insert(0, task)
            elif group_name == "done" and task.get("column") != "done":
                tasks.remove(task)
                grouped.setdefault("today", [])
                grouped["today"].insert(0, task)
            return with_task_assignee(employee_id, task)
    raise NotFound(detail="Task not found.")


def delete_workspace_task(employee_id: str, task_id: str) -> None:
    grouped = EMPLOYEE_VERTICAL_TASKS.get(employee_id)
    if not grouped:
        raise NotFound(detail=f"Employee '{employee_id}' not found.")
    for _, tasks in grouped.items():
        for task in list(tasks):
            if str(task.get("id")) == str(task_id):
                tasks.remove(task)
                return
    raise NotFound(detail="Task not found.")


def _seed_demo_workspace_task_threads() -> None:
    ts = "2026-04-10T09:00:00Z"
    _TASK_THREADS[_task_thread_key("emp-1", "t-over-1")] = {
        "audit": [
            {
                "id": "audit-seed-1",
                "action": "created",
                "actor_name": "Alex Kim",
                "actor_role": "employee",
                "timestamp": ts,
                "details": "Демо: задача из seed-данных",
            },
        ],
        "comments": [
            {
                "id": "c-seed-1",
                "message": "Уточнить слайды для KPI",
                "author_name": "Alex Kim",
                "author_role": "employee",
                "created_at": ts,
            },
        ],
        "checklist": [
            {"id": "cl-seed-1", "title": "Собрать метрики", "done": False, "position": 1},
            {"id": "cl-seed-2", "title": "Согласовать с PM", "done": True, "position": 2},
        ],
    }


_seed_demo_workspace_task_threads()
