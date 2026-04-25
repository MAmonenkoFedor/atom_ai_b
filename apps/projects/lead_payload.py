"""Сводка по руководителю проекта для списка/карточки: глава, пакетные права, аудит."""

from __future__ import annotations

from django.contrib.auth import get_user_model

from apps.access.models import PermissionDefinition, PermissionGrant, SCOPE_PROJECT
from apps.audit.models import AuditEvent
from apps.projects.models import ProjectMember

User = get_user_model()

PROJECT_LEAD_HISTORY_TYPES = ("project.project_lead_set", "project.project_lead_cleared")
HISTORY_PER_PROJECT = 8


def project_lead_scoped_note(project_id: int) -> str:
    return f"project_lead_scoped:proj={int(project_id)}"


def _user_label(u) -> str:
    if not u:
        return "—"
    return (u.get_full_name() or getattr(u, "username", None) or "").strip() or "—"


def batch_project_lead_payload(project_ids: list[int]) -> dict[int, dict]:
    """project_id -> поля для сериализатора проекта."""
    if not project_ids:
        return {}
    str_ids = [str(pid) for pid in project_ids]
    lead_rows: dict[int, object] = {}
    for m in (
        ProjectMember.objects.filter(
            project_id__in=project_ids, is_active=True, is_lead=True
        ).select_related("user")
    ):
        lead_rows[m.project_id] = m.user

    note_in = [project_lead_scoped_note(pid) for pid in project_ids]
    gmap: dict[tuple[int, int], list[str]] = {}
    for g in PermissionGrant.objects.filter(
        status=PermissionGrant.STATUS_ACTIVE,
        scope_type=SCOPE_PROJECT,
        note__in=note_in,
    ).values("employee_id", "permission_code", "scope_id"):
        sid = (g.get("scope_id") or "").strip()
        if not sid.isdigit():
            continue
        k = (int(sid), int(g["employee_id"]))
        gmap.setdefault(k, []).append(g["permission_code"])
    all_codes: set[str] = set()
    for codes in gmap.values():
        all_codes.update(codes)
    code_names: dict[str, str] = {}
    if all_codes:
        for row in PermissionDefinition.objects.filter(code__in=sorted(all_codes)).values("code", "name"):
            code_names[row["code"]] = row["name"]

    h_buf: dict[int, list] = {pid: [] for pid in project_ids}
    event_cap = min(2000, max(80, 12 * len(project_ids)))
    for ev in (
        AuditEvent.objects.filter(
            entity_type="project",
            entity_id__in=str_ids,
            event_type__in=PROJECT_LEAD_HISTORY_TYPES,
        )
        .select_related("actor")
        .order_by("-created_at")[:event_cap]
    ):
        eid = int(ev.entity_id) if (ev.entity_id or "").isdigit() else None
        if eid is None or eid not in h_buf:
            continue
        if len(h_buf[eid]) >= HISTORY_PER_PROJECT:
            continue
        h_buf[eid].append(ev)
    subj_ids: set[int] = set()
    for el in h_buf.values():
        for ev in el:
            raw = (ev.payload or {}).get("user_id")
            if raw is not None and str(raw).isdigit():
                subj_ids.add(int(raw))
    subj_name: dict[int, str] = {}
    if subj_ids:
        for u in User.objects.filter(id__in=subj_ids):
            subj_name[u.id] = _user_label(u)

    out: dict[int, dict] = {}
    for pid in project_ids:
        u = lead_rows.get(pid)
        if u:
            lead_name = (u.get_full_name() or u.username or "").strip() or "-"
        else:
            lead_name = "-"
        p_codes: list[str] = []
        if u:
            p_codes = sorted(gmap.get((pid, u.id), []))
        bundle = [{"code": c, "name": code_names.get(c) or c} for c in p_codes]
        history: list[dict] = []
        for ev in h_buf.get(pid, []):
            p = ev.payload or {}
            suid = p.get("user_id")
            sid_int = int(suid) if suid is not None and str(suid).isdigit() else None
            history.append(
                {
                    "at": ev.created_at.isoformat(),
                    "action": ev.action,
                    "event_type": ev.event_type,
                    "actor_id": ev.actor_id,
                    "actor_name": _user_label(ev.actor) if ev.actor else "—",
                    "subject_user_id": suid,
                    "subject_name": (subj_name.get(sid_int) if sid_int is not None else "—")
                    or "—",
                    "grant_project_edit": p.get("grant_project_edit"),
                    "grant_project_assign_members": p.get("grant_project_assign_members"),
                    "grant_project_docs_view": p.get("grant_project_docs_view"),
                    "grant_project_docs_upload": p.get("grant_project_docs_upload"),
                    "grant_project_docs_edit": p.get("grant_project_docs_edit"),
                    "grant_project_docs_assign_editors": p.get("grant_project_docs_assign_editors"),
                    "grant_project_tasks_view": p.get("grant_project_tasks_view"),
                    "grant_project_tasks_create": p.get("grant_project_tasks_create"),
                    "grant_project_tasks_assign": p.get("grant_project_tasks_assign"),
                    "grant_project_tasks_change_deadline": p.get("grant_project_tasks_change_deadline"),
                }
            )
        out[pid] = {
            "project_lead_id": u.id if u else None,
            "project_lead": lead_name,
            "project_lead_email": (u.email or "").strip() if u else "",
            "lead_bundle_permissions": bundle,
            "lead_history": history,
        }
    return out
