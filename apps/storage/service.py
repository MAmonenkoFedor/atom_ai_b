from __future__ import annotations

from collections import defaultdict

from django.db.models import Q

from apps.projects.models import ProjectDocument
from apps.workspaces.models import WorkspaceCabinetDocument


def _safe_file_size(obj) -> int:
    f = getattr(obj, "file", None)
    if not f:
        return 0
    try:
        return int(f.size or 0)
    except OSError:
        return 0


def _stored_upload_bytes(obj) -> int:
    ub = int(getattr(obj, "upload_stored_bytes", 0) or 0)
    if ub > 0:
        return ub
    return _safe_file_size(obj)


def compute_storage_usage() -> dict:
    """Aggregate uploaded file bytes from workspace cabinet + project documents."""

    total = 0
    by_user: dict[int, int] = defaultdict(int)
    by_project: dict[int, int] = defaultdict(int)
    by_org: dict[int, int] = defaultdict(int)
    workspace_bytes = 0
    project_bytes = 0

    ws_upload_q = Q(source=WorkspaceCabinetDocument.Source.UPLOAD) & (
        Q(upload_stored_bytes__gt=0) | ~Q(file="")
    )

    for doc in (
        WorkspaceCabinetDocument.objects.filter(ws_upload_q)
        .select_related("user")
        .iterator(chunk_size=500)
    ):
        sz = _stored_upload_bytes(doc)
        if sz <= 0:
            continue
        workspace_bytes += sz
        total += sz
        by_user[doc.user_id] += sz

    pd_upload_q = Q(source=ProjectDocument.Source.UPLOAD) & (Q(upload_stored_bytes__gt=0) | ~Q(file=""))

    for doc in (
        ProjectDocument.objects.filter(pd_upload_q)
        .select_related("project", "uploaded_by")
        .iterator(chunk_size=500)
    ):
        sz = _stored_upload_bytes(doc)
        if sz <= 0:
            continue
        project_bytes += sz
        total += sz
        by_project[doc.project_id] += sz
        org_id = getattr(doc.project, "organization_id", None)
        if org_id:
            by_org[int(org_id)] += sz
        if doc.uploaded_by_id:
            by_user[doc.uploaded_by_id] += sz

    return {
        "total_bytes": total,
        "workspace_uploads_bytes": workspace_bytes,
        "project_uploads_bytes": project_bytes,
        "by_user": [{"user_id": str(uid), "bytes": b} for uid, b in sorted(by_user.items())],
        "by_project": [{"project_id": str(pid), "bytes": b} for pid, b in sorted(by_project.items())],
        "by_organization": [{"organization_id": str(oid), "bytes": b} for oid, b in sorted(by_org.items())],
    }
