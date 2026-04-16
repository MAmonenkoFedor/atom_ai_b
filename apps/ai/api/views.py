from datetime import datetime, time

from django.utils import dateparse
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.ai.models import AiRun
from apps.llm_gateway.models import LlmRequestLog
from apps.llm_gateway.services import LlmGatewayService

from .serializers import (
    AiRunCreateSerializer,
    AiRunExecuteSerializer,
    AiRunLogSerializer,
    AiRunSerializer,
)


class AiRunCreateView(generics.CreateAPIView):
    queryset = AiRun.objects.select_related("project", "chat", "message", "requested_by")
    serializer_class = AiRunCreateSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ai_run = serializer.save(
            requested_by=request.user,
            status=AiRun.STATUS_PENDING,
        )
        return Response(AiRunSerializer(ai_run).data, status=status.HTTP_201_CREATED)


class AiRunDetailView(generics.RetrieveAPIView):
    queryset = AiRun.objects.select_related("project", "chat", "message", "requested_by")
    serializer_class = AiRunSerializer
    permission_classes = [IsAuthenticated]


class AiRunExecuteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        ai_run = generics.get_object_or_404(
            AiRun.objects.select_related("message", "project", "chat"),
            pk=pk,
        )

        input_serializer = AiRunExecuteSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        profile = input_serializer.validated_data.get("profile", "chat_balanced")
        prompt = input_serializer.validated_data.get("prompt")
        if not prompt:
            prompt = ai_run.message.content if ai_run.message_id else "Continue conversation."

        ai_run.status = AiRun.STATUS_RUNNING
        ai_run.started_at = timezone.now()
        ai_run.error_message = ""
        ai_run.save(update_fields=["status", "started_at", "error_message"])

        gateway = LlmGatewayService()
        try:
            result = gateway.execute(
                ai_run=ai_run,
                prompt=prompt,
                profile_code=profile,
                requested_provider_code=ai_run.provider or None,
                requested_model_code=ai_run.model or None,
            )
            ai_run.status = AiRun.STATUS_COMPLETED
            ai_run.provider = result["provider_code"]
            ai_run.model = result["model_code"]
            ai_run.output_text = result["text"]
            ai_run.usage = result["usage"]
            ai_run.citations = []
            ai_run.completed_at = timezone.now()
            ai_run.error_message = ""
            ai_run.save(
                update_fields=[
                    "status",
                    "provider",
                    "model",
                    "output_text",
                    "usage",
                    "citations",
                    "completed_at",
                    "error_message",
                ]
            )
        except Exception as exc:
            ai_run.status = AiRun.STATUS_FAILED
            ai_run.error_message = str(exc)
            ai_run.completed_at = timezone.now()
            ai_run.save(update_fields=["status", "error_message", "completed_at"])

        return Response(AiRunSerializer(ai_run).data, status=status.HTTP_200_OK)


class AiRunLogsView(generics.ListAPIView):
    serializer_class = AiRunLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Ensure ai_run exists first for stable 404 behavior.
        generics.get_object_or_404(AiRun, pk=self.kwargs["pk"])
        qs = LlmRequestLog.objects.select_related("provider", "model", "profile").filter(
            ai_run_id=self.kwargs["pk"]
        )
        status_param = self.request.query_params.get("status")
        provider_param = self.request.query_params.get("provider")
        limit_param = self.request.query_params.get("limit")
        sort_param = self.request.query_params.get("sort", "-created_at")
        from_param = self.request.query_params.get("from")
        to_param = self.request.query_params.get("to")
        has_error_param = self.request.query_params.get("has_error")
        min_latency_param = self.request.query_params.get("min_latency_ms")

        if status_param:
            qs = qs.filter(status=status_param)

        if provider_param:
            qs = qs.filter(provider__code=provider_param)

        if has_error_param is not None:
            normalized = has_error_param.strip().lower()
            if normalized in {"true", "1", "yes"}:
                qs = qs.filter(status=LlmRequestLog.STATUS_ERROR)
            elif normalized in {"false", "0", "no"}:
                qs = qs.filter(status=LlmRequestLog.STATUS_SUCCESS)
            else:
                raise ValidationError(
                    {"detail": "Invalid has_error. Allowed: true/false, 1/0, yes/no."}
                )

        if min_latency_param is not None:
            try:
                min_latency = int(min_latency_param)
            except ValueError as exc:
                raise ValidationError(
                    {"detail": "Invalid min_latency_ms. Must be a non-negative integer."}
                ) from exc
            if min_latency < 0:
                raise ValidationError(
                    {"detail": "Invalid min_latency_ms. Must be a non-negative integer."}
                )
            qs = qs.filter(latency_ms__gte=min_latency)

        if from_param:
            from_dt = self._parse_datetime_param(from_param, "from", is_end=False)
            qs = qs.filter(created_at__gte=from_dt)

        if to_param:
            to_dt = self._parse_datetime_param(to_param, "to", is_end=True)
            qs = qs.filter(created_at__lte=to_dt)

        allowed_sort = {
            "created_at",
            "-created_at",
            "latency_ms",
            "-latency_ms",
            "total_tokens",
            "-total_tokens",
        }
        if sort_param not in allowed_sort:
            raise ValidationError(
                {
                    "detail": "Invalid sort. Allowed: created_at, -created_at, "
                    "latency_ms, -latency_ms, total_tokens, -total_tokens."
                }
            )
        qs = qs.order_by(sort_param)

        if limit_param:
            try:
                limit = max(1, min(200, int(limit_param)))
                qs = qs[:limit]
            except ValueError:
                raise ValidationError({"detail": "Invalid limit. Must be an integer."})

        return qs

    @staticmethod
    def _parse_datetime_param(raw: str, param_name: str, *, is_end: bool):
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
