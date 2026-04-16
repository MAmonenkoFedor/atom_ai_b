from copy import deepcopy

from rest_framework.exceptions import NotFound

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
                        "due": "2026-04-20",
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
                "due": "2026-04-20",
            }
        ],
        "documents": [
            {
                "id": "doc-1",
                "title": "Marketing roadmap Q2",
                "type": "doc",
                "updated_at": "2026-04-14T10:42:00+03:00",
                "owner": "Alex K",
            }
        ],
        "activity_feed": [
            {
                "id": "act-1",
                "type": "task",
                "title": "Task updated",
                "timestamp": "2026-04-14T11:10:00+03:00",
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
                "timestamp": "2026-04-14T11:10:00+03:00",
            }
        ],
        "comments_history": [
            {
                "id": "cmt-1",
                "author": "Alex K",
                "text": "Need KPI update",
                "created_at": "2026-04-14T10:10:00+03:00",
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
