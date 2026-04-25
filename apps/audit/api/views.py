import csv
from collections import defaultdict
from datetime import datetime, time
from io import StringIO

from django.db.models import Q
from django.http import StreamingHttpResponse
from django.utils import dateparse, timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditEvent

from .serializers import AuditEventSerializer


CSV_EXPORT_LIMIT = 50_000


def _parse_audit_datetime(raw: str, param_name: str, *, is_end: bool):
    dt = dateparse.parse_datetime(raw)
    if dt is not None:
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt

    d = dateparse.parse_date(raw)
    if d is not None:
        boundary_time = time.max if is_end else time.min
        dt = datetime.combine(d, boundary_time)
        return timezone.make_aware(dt, timezone.get_current_timezone())

    raise ValidationError(
        {
            "detail": (
                f"Invalid {param_name}. Use ISO datetime "
                f"(e.g. 2026-04-14T10:00:00+03:00) or date (YYYY-MM-DD)."
            )
        }
    )


def _get_role_code(request):
    role_assignment = request.user.role_assignments.select_related("role").first()
    return role_assignment.role.code if role_assignment and role_assignment.role else ""


def _ensure_audit_permissions(request):
    role_code = _get_role_code(request)
    if role_code not in {"super_admin", "admin"}:
        raise PermissionDenied("Only super admin can view audit events.")


def _apply_audit_filters(request, qs):
    q = (request.query_params.get("q") or "").strip()
    actor_id = request.query_params.get("actor_id")
    event_type = request.query_params.get("event_type")
    entity_type = request.query_params.get("entity_type")
    project_id = request.query_params.get("project_id")
    task_id = request.query_params.get("task_id")
    chat_id = request.query_params.get("chat_id")
    from_dt = request.query_params.get("from")
    to_dt = request.query_params.get("to")

    if actor_id:
        qs = qs.filter(actor_id=actor_id)
    if event_type:
        qs = qs.filter(event_type=event_type)
    if entity_type:
        qs = qs.filter(entity_type=entity_type)
    if project_id:
        qs = qs.filter(project_id=project_id)
    if task_id:
        qs = qs.filter(task_id=task_id)
    if chat_id:
        qs = qs.filter(chat_id=chat_id)
    if from_dt:
        qs = qs.filter(created_at__gte=_parse_audit_datetime(from_dt, "from", is_end=False))
    if to_dt:
        qs = qs.filter(created_at__lte=_parse_audit_datetime(to_dt, "to", is_end=True))
    if q:
        qs = qs.filter(
            Q(event_type__icontains=q)
            | Q(entity_type__icontains=q)
            | Q(entity_id__icontains=q)
            | Q(actor__username__icontains=q)
            | Q(request_path__icontains=q)
            | Q(project_id__icontains=q)
            | Q(task_id__icontains=q)
            | Q(chat_id__icontains=q)
        )
    return qs


class AuditEventListView(generics.ListAPIView):
    serializer_class = AuditEventSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="auditEventsList",
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR),
            OpenApiParameter("actor_id", OpenApiTypes.INT),
            OpenApiParameter("event_type", OpenApiTypes.STR),
            OpenApiParameter("entity_type", OpenApiTypes.STR),
            OpenApiParameter("project_id", OpenApiTypes.STR),
            OpenApiParameter("task_id", OpenApiTypes.STR),
            OpenApiParameter("chat_id", OpenApiTypes.STR),
            OpenApiParameter("from", OpenApiTypes.DATETIME),
            OpenApiParameter("to", OpenApiTypes.DATETIME),
            OpenApiParameter("page", OpenApiTypes.INT),
            OpenApiParameter("page_size", OpenApiTypes.INT),
        ],
        responses=AuditEventSerializer(many=True),
    )
    def get_queryset(self):
        _ensure_audit_permissions(self.request)
        qs = AuditEvent.objects.select_related("actor").all()
        return _apply_audit_filters(self.request, qs)


class AuditEventStatsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="auditEventsStats",
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR),
            OpenApiParameter("actor_id", OpenApiTypes.INT),
            OpenApiParameter("event_type", OpenApiTypes.STR),
            OpenApiParameter("entity_type", OpenApiTypes.STR),
            OpenApiParameter("project_id", OpenApiTypes.STR),
            OpenApiParameter("task_id", OpenApiTypes.STR),
            OpenApiParameter("chat_id", OpenApiTypes.STR),
            OpenApiParameter("from", OpenApiTypes.DATETIME),
            OpenApiParameter("to", OpenApiTypes.DATETIME),
        ],
        responses={
            200: OpenApiTypes.OBJECT,
        },
    )
    def get(self, request):
        _ensure_audit_permissions(request)
        qs = _apply_audit_filters(request, AuditEvent.objects.all())
        critical_action_values = ("delete", "remove", "archive", "revoke", "fail", "error")
        critical_q = Q()
        for marker in critical_action_values:
            critical_q |= Q(action__icontains=marker) | Q(event_type__icontains=marker)
        stats = {
            "events_total": qs.count(),
            "ai_failures": qs.filter(
                Q(event_type__icontains="ai")
                & (Q(event_type__icontains="fail") | Q(action__icontains="fail"))
            ).count(),
            "unique_actors": qs.exclude(actor_id__isnull=True).values("actor_id").distinct().count(),
            "critical_actions": qs.filter(critical_q).count(),
            "critical_action_types": list(critical_action_values),
        }
        return Response(stats)


class AuditEventsExportView(APIView):
    """Stream filtered audit events as CSV.

    Respects the same filter params as the list view. Hard-capped at
    ``CSV_EXPORT_LIMIT`` rows to avoid unbounded memory/IO.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="auditEventsExportCsv",
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR),
            OpenApiParameter("actor_id", OpenApiTypes.INT),
            OpenApiParameter("event_type", OpenApiTypes.STR),
            OpenApiParameter("entity_type", OpenApiTypes.STR),
            OpenApiParameter("project_id", OpenApiTypes.STR),
            OpenApiParameter("task_id", OpenApiTypes.STR),
            OpenApiParameter("chat_id", OpenApiTypes.STR),
            OpenApiParameter("from", OpenApiTypes.DATETIME),
            OpenApiParameter("to", OpenApiTypes.DATETIME),
            OpenApiParameter("limit", OpenApiTypes.INT),
        ],
        responses={200: OpenApiTypes.BINARY},
    )
    def get(self, request):
        _ensure_audit_permissions(request)
        qs = _apply_audit_filters(
            request, AuditEvent.objects.select_related("actor").all()
        )
        try:
            limit = int(request.query_params.get("limit") or CSV_EXPORT_LIMIT)
        except (TypeError, ValueError):
            limit = CSV_EXPORT_LIMIT
        limit = max(1, min(limit, CSV_EXPORT_LIMIT))

        columns = (
            "id",
            "created_at",
            "event_type",
            "entity_type",
            "entity_id",
            "action",
            "actor_id",
            "actor_username",
            "actor_role",
            "company_id",
            "department_id",
            "project_id",
            "task_id",
            "chat_id",
            "request_method",
            "request_path",
            "ip_address",
            "trace_id",
        )

        def row(ev: AuditEvent) -> list:
            return [
                ev.id,
                ev.created_at.isoformat() if ev.created_at else "",
                ev.event_type,
                ev.entity_type,
                ev.entity_id,
                ev.action,
                ev.actor_id or "",
                getattr(ev.actor, "username", "") or "",
                ev.actor_role,
                ev.company_id,
                ev.department_id,
                ev.project_id,
                ev.task_id,
                ev.chat_id,
                ev.request_method,
                ev.request_path,
                ev.ip_address or "",
                ev.trace_id,
            ]

        def stream():
            buffer = StringIO()
            writer = csv.writer(buffer)
            writer.writerow(columns)
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)
            for ev in qs[:limit].iterator(chunk_size=500):
                writer.writerow(row(ev))
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate(0)

        filename = (
            f"atom-audit-events-{timezone.now().strftime('%Y%m%d-%H%M%S')}.csv"
        )
        response = StreamingHttpResponse(stream(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["X-Content-Type-Options"] = "nosniff"
        return response


class AiUsageStatsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="aiUsageStats",
        parameters=[
            OpenApiParameter("from", OpenApiTypes.DATETIME),
            OpenApiParameter("to", OpenApiTypes.DATETIME),
            OpenApiParameter("chat_id", OpenApiTypes.STR),
            OpenApiParameter("project_id", OpenApiTypes.STR),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        _ensure_audit_permissions(request)
        qs = _apply_audit_filters(request, AuditEvent.objects.all()).filter(
            event_type="ai.chat_completion_created"
        )
        totals = {
            "requests": qs.count(),
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cost_estimate": 0.0,
        }
        by_actor: dict[str, dict] = defaultdict(
            lambda: {
                "actor_id": None,
                "actor_username": "",
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cost_estimate": 0.0,
            }
        )
        by_chat: dict[str, dict] = defaultdict(
            lambda: {
                "chat_id": "",
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cost_estimate": 0.0,
            }
        )
        for event in qs.iterator(chunk_size=500):
            payload = event.payload or {}
            in_tok = int(payload.get("input_tokens") or 0)
            out_tok = int(payload.get("output_tokens") or 0)
            tot_tok = int(payload.get("total_tokens") or (in_tok + out_tok))
            cost = float(payload.get("cost_estimate") or 0.0)
            totals["input_tokens"] += in_tok
            totals["output_tokens"] += out_tok
            totals["total_tokens"] += tot_tok
            totals["cost_estimate"] += cost

            actor_key = str(event.actor_id or "unknown")
            actor_row = by_actor[actor_key]
            actor_row["actor_id"] = event.actor_id
            actor_row["actor_username"] = getattr(event.actor, "username", "") if event.actor else ""
            actor_row["requests"] += 1
            actor_row["input_tokens"] += in_tok
            actor_row["output_tokens"] += out_tok
            actor_row["total_tokens"] += tot_tok
            actor_row["cost_estimate"] += cost

            chat_key = str(event.chat_id or "")
            chat_row = by_chat[chat_key]
            chat_row["chat_id"] = chat_key
            chat_row["requests"] += 1
            chat_row["input_tokens"] += in_tok
            chat_row["output_tokens"] += out_tok
            chat_row["total_tokens"] += tot_tok
            chat_row["cost_estimate"] += cost

        return Response(
            {
                "totals": totals,
                "by_actor": sorted(by_actor.values(), key=lambda x: x["requests"], reverse=True),
                "by_chat": sorted(by_chat.values(), key=lambda x: x["requests"], reverse=True),
            }
        )
