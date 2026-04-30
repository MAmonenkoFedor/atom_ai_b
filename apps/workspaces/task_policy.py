"""Workspace task access: combines employee bucket scope with optional project cap."""

from __future__ import annotations

from types import SimpleNamespace

from rest_framework.exceptions import PermissionDenied

_LEVEL_ORDER = ("none", "metadata", "read", "write", "manage", "admin")


def _level_index(level: str) -> int:
    try:
        return _LEVEL_ORDER.index(level)
    except ValueError:
        return 0


def _weaker_level(a: str, b: str) -> str:
    return _LEVEL_ORDER[min(_level_index(a), _level_index(b))]


def normalize_workspace_task_resource(resource, scope_id: str | None) -> tuple[str | None, dict | None]:
    """Return ``(employee_id, task_dict)`` from a ``SimpleNamespace`` / object or ``(None, None)``."""

    if resource is None:
        return None, None
    employee_id = getattr(resource, "employee_id", None)
    if employee_id is not None:
        employee_id = str(employee_id).strip() or None
    task = getattr(resource, "task", None)
    if task is not None and not isinstance(task, dict):
        task = None
    return employee_id, task


def resolve_workspace_task_project(task: dict | None):
    if not task:
        return None
    raw = task.get("project_id")
    if raw in (None, ""):
        return None
    from apps.projects.models import Project

    try:
        pk = int(raw)
    except (TypeError, ValueError):
        return None
    return Project.objects.filter(pk=pk).first()


def compute_workspace_task_policy_decision(*, user, employee_id: str, task: dict | None):
    """Maximum effective access level for workspace (employee-vertical) tasks."""

    from apps.access.policies import PolicyDecision
    from apps.projects.project_permissions import compute_project_policy_decision, is_privileged_project_viewer
    from apps.workspaces import data as workspace_data

    subject_id = int(getattr(user, "id", 0) or 0)
    tid = str((task or {}).get("id") or "").strip()
    scope_sid = tid or f"bucket:{employee_id}"

    if not user or not getattr(user, "is_authenticated", False):
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason="anonymous",
            scope_type="task",
            scope_id=scope_sid,
            subject_id=subject_id,
            object_id=None,
        )

    viewer_eid = workspace_data.resolve_employee_id_for_username(user.username)
    project = resolve_workspace_task_project(task)
    project_level = "admin"
    if project is not None:
        pd = compute_project_policy_decision(user, project)
        project_level = pd.access_level if pd.allowed else "none"

    if employee_id != viewer_eid:
        if bool(getattr(user, "is_superuser", False)):
            worker = "admin"
        elif is_privileged_project_viewer(user):
            worker = "manage"
        else:
            return PolicyDecision(
                allowed=False,
                access_level="none",
                reason="workspace_scope_mismatch",
                scope_type="task",
                scope_id=scope_sid,
                subject_id=subject_id,
                object_id=None,
            )
    else:
        worker = "write"

    effective = _weaker_level(worker, project_level)
    if effective == "none":
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason="project_cap_blocks_task",
            scope_type="task",
            scope_id=scope_sid,
            subject_id=subject_id,
            object_id=None,
        )

    return PolicyDecision(
        allowed=True,
        access_level=effective,
        reason="workspace_task",
        scope_type="task",
        scope_id=scope_sid,
        subject_id=subject_id,
        object_id=None,
    )


def require_workspace_task_access(
    user,
    employee_id: str,
    action: str,
    *,
    task_id: str | None = None,
    message: str = "You do not have permission for this task operation.",
):
    """Load task row when ``task_id`` is set, then ``resolve_access`` on ``scope_type=\"task\"``."""

    from apps.access.policies import resolve_access
    from apps.workspaces import data as workspace_data

    task = None
    if task_id:
        task = workspace_data.get_workspace_task(employee_id, task_id)
    resource = SimpleNamespace(employee_id=employee_id, task=task)
    d = resolve_access(
        user=user,
        action=action,
        scope_type="task",
        scope_id=str(task_id or ""),
        resource=resource,
    )
    if not d.allowed:
        raise PermissionDenied(message)
    return d


def require_workspace_task_read_or_metadata(
    user,
    employee_id: str,
    *,
    task_id: str | None = None,
    message: str = "You do not have permission to view workspace tasks.",
):
    """Try ``task.read``, then ``task.view_metadata`` (project metadata-only cap)."""

    from apps.access.policies import resolve_access
    from apps.workspaces import data as workspace_data

    task = None
    if task_id:
        task = workspace_data.get_workspace_task(employee_id, task_id)
    resource = SimpleNamespace(employee_id=employee_id, task=task)
    sid = str(task_id or "")
    for action in ("task.read", "task.view_metadata"):
        d = resolve_access(
            user=user,
            action=action,
            scope_type="task",
            scope_id=sid,
            resource=resource,
        )
        if d.allowed:
            return d
    raise PermissionDenied(message)
