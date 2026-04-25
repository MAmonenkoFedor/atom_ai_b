"""Task counters per project for Project context counts."""

from __future__ import annotations


def get_task_counts_by_project_id() -> dict[int, dict[str, int]]:
    """
    Build {project_id: {tasks_total, tasks_open}} from current task source.
    Falls back to empty mapping if task source is unavailable.
    """
    try:
        # Current task contract source is in-memory parallel contract payload.
        from apps.core.api.parallel_contract_views import TASK_ITEMS
    except Exception:
        return {}

    counts: dict[int, dict[str, int]] = {}
    for task in TASK_ITEMS:
        raw_project_id = task.get("project_id")
        if raw_project_id in (None, ""):
            continue
        try:
            project_id = int(raw_project_id)
        except (TypeError, ValueError):
            continue
        bucket = counts.setdefault(project_id, {"tasks_total": 0, "tasks_open": 0})
        bucket["tasks_total"] += 1
        status = str(task.get("status") or "").lower()
        if status not in {"done", "completed", "archived"}:
            bucket["tasks_open"] += 1
    return counts
