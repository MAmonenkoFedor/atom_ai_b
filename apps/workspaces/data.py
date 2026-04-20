from copy import deepcopy
from datetime import datetime, timezone
from itertools import count

from rest_framework.exceptions import NotFound, ValidationError

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
        "logo": "https://cdn.atom.ai/assets/bcs-drift-logo.png",
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
                "avatar": "https://cdn.atom.ai/assets/avatars/emp-1.png",
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
            "avatar": "https://cdn.atom.ai/assets/avatars/emp-1.png",
            "department": "Marketing",
            "status": "online",
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
        ],
    },
    "emp-2": {
        "header": {
            "id": "emp-2",
            "full_name": "Maria Smirnova",
            "role": "manager",
            "title": "Marketing Manager",
            "avatar": "https://cdn.atom.ai/assets/avatars/emp-2.png",
            "department": "Marketing",
            "status": "online",
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
        ],
    },
    "emp-3": {
        "header": {
            "id": "emp-3",
            "full_name": "Company Admin",
            "role": "company_admin",
            "title": "Company Admin",
            "avatar": "https://cdn.atom.ai/assets/avatars/emp-3.png",
            "department": "Administration",
            "status": "online",
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

_quick_task_seq = count(2000)


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
    return {
        "employee": employee,
        "my_tasks": deepcopy(extra.get("my_tasks", [])),
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
    return USERNAME_TO_EMPLOYEE.get(username, "emp-1")


def _role_extras(role_code: str) -> dict | None:
    if role_code == "manager":
        return {"kind": "manager", "team_size": 7, "at_risk_tasks": 1}
    if role_code == "company_admin":
        return {"kind": "admin", "alerts": 2, "pending_invites": 1}
    if role_code == "executive":
        return {"kind": "executive", "attention_buildings": 1}
    return None


def _grouped_tasks_payload(employee_id: str) -> list[dict]:
    tasks = EMPLOYEE_VERTICAL_TASKS.get(employee_id, {"overdue": [], "today": [], "this_week": [], "later": [], "done": []})
    labels = {
        "overdue": "Просрочено",
        "today": "Сегодня",
        "this_week": "На этой неделе",
        "later": "Позже",
        "done": "Сделано",
    }
    return [{"key": key, "label": labels[key], "tasks": deepcopy(tasks.get(key, []))} for key in ["overdue", "today", "this_week", "later", "done"]]


def get_employee_workspace(employee_id: str, viewer_role: str) -> dict:
    profile = deepcopy(EMPLOYEE_VERTICAL_DIRECTORY.get(employee_id))
    if not profile:
        raise NotFound(detail=f"Employee '{employee_id}' not found.")
    grouped = _grouped_tasks_payload(employee_id)
    tasks_count = sum(len(group["tasks"]) for group in grouped)
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
            {"id": "qa-1", "kind": "create_task", "label": "Новая задача"},
            {"id": "qa-2", "kind": "open_ai", "label": "Спросить AI"},
            {"id": "qa-3", "kind": "new_note", "label": "Заметка"},
        ],
        "stats": {
            "tasks_in_progress": tasks_count - done_count,
            "tasks_done": done_count,
            "tasks_overdue": overdue_count,
            "streak_days": 4,
            "week_balance": 78,
        },
        "tasks_grouped": grouped,
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
    }
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

    for key in ["personal_email", "phone", "telegram", "city", "working_hours", "timezone"]:
        if key in patch:
            profile["contacts"][key] = patch[key]
    if "preferences" in patch and isinstance(patch["preferences"], dict):
        profile["preferences"].update(patch["preferences"])
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
    return items


def get_workspace_task(employee_id: str, task_id: str) -> dict:
    for task in _all_employee_tasks(employee_id):
        if str(task.get("id")) == str(task_id):
            return task
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
    EMPLOYEE_VERTICAL_TASKS[employee_id][target_group].insert(0, task)
    return task


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
            return deepcopy(task)
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
