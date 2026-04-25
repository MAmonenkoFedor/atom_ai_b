from __future__ import annotations

from apps.audit.models import AuditEvent


def _client_ip(request) -> str | None:
    xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def emit_audit_event(
    request,
    *,
    event_type: str,
    entity_type: str,
    action: str,
    entity_id: str = "",
    project_id: str = "",
    task_id: str = "",
    chat_id: str = "",
    payload: dict | None = None,
) -> AuditEvent:
    user = getattr(request, "user", None)
    role = ""
    company_id = ""
    department_id = ""
    if user and user.is_authenticated:
        assignment = user.role_assignments.select_related("role").first()
        if assignment and assignment.role:
            role = assignment.role.code
        company_id = str(getattr(user, "organization_id", "") or "")
        department_id = str(getattr(user, "department_id", "") or "")

    trace_id = (
        request.headers.get("X-Trace-Id")
        or request.headers.get("X-Request-Id")
        or request.META.get("HTTP_X_TRACE_ID")
        or request.META.get("HTTP_X_REQUEST_ID")
        or ""
    )
    return AuditEvent.objects.create(
        actor=user if (user and user.is_authenticated) else None,
        actor_role=role,
        company_id=company_id,
        department_id=department_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        project_id=project_id,
        task_id=task_id,
        chat_id=chat_id,
        request_path=request.path,
        request_method=request.method,
        ip_address=_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:512],
        trace_id=trace_id[:64],
        payload=payload or {},
    )
