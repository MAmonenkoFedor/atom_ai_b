from datetime import datetime, time

from django.conf import settings
from django.core.cache import cache
from django.utils import dateparse
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.audit.service import emit_audit_event
from apps.ai.models import AiRun
from apps.chats.models import Chat, ChatAttachment, Message
from apps.llm_gateway.models import LlmRequestLog
from apps.llm_gateway.services import LlmGatewayService
from apps.organizations.models import OrganizationMember
from apps.projects.models import Project, ProjectDocument
from apps.workspaces.models import WorkspaceCabinetDocument
from apps.workspaces import data as workspace_data

from .serializers import (
    AiChatAllowedModelSerializer,
    AiChatCompletionsRequestSerializer,
    AiRunCreateSerializer,
    AiRunExecuteSerializer,
    AiRunLogSerializer,
    AiRunSerializer,
)
from apps.ai.providers import OpenRouterProvider


class AiModelsListView(APIView):
    """Return the curated whitelist of AI models available to users.

    The list is defined in ``settings.AI_CHAT_ALLOWED_MODELS`` and controlled
    by the platform admin. The default model (``settings.DEFAULT_AI_MODEL``)
    is marked via ``is_default=True`` in the payload whenever it appears in the
    whitelist; if it does not appear, the first whitelisted model is returned
    as the default.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        raw_models = list(getattr(settings, "AI_CHAT_ALLOWED_MODELS", []) or [])
        default_model_id = str(getattr(settings, "DEFAULT_AI_MODEL", "") or "")
        known_default = any(entry.get("id") == default_model_id for entry in raw_models)
        if not known_default and raw_models:
            default_model_id = str(raw_models[0].get("id") or "")

        results = []
        for entry in raw_models:
            payload = dict(entry)
            payload["is_default"] = str(payload.get("id") or "") == default_model_id
            results.append(payload)

        serializer = AiChatAllowedModelSerializer(results, many=True)
        return Response(
            {
                "results": serializer.data,
                "default_model": default_model_id,
            },
            status=status.HTTP_200_OK,
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
        emit_audit_event(
            request,
            event_type="ai.run_created",
            entity_type="ai_run",
            action="create",
            entity_id=str(ai_run.pk),
            project_id=str(ai_run.project_id or ""),
            chat_id=str(ai_run.chat_id or ""),
            payload={"provider": ai_run.provider, "model": ai_run.model},
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
            emit_audit_event(
                request,
                event_type="ai.chat_prompt_executed",
                entity_type="ai_run",
                action="execute",
                entity_id=str(ai_run.pk),
                project_id=str(ai_run.project_id or ""),
                chat_id=str(ai_run.chat_id or ""),
                payload={
                    "provider": ai_run.provider,
                    "model": ai_run.model,
                    "prompt_len": len(prompt or ""),
                    "total_tokens": int((ai_run.usage or {}).get("total_tokens", 0)),
                },
            )
        except Exception as exc:
            ai_run.status = AiRun.STATUS_FAILED
            ai_run.error_message = str(exc)
            ai_run.completed_at = timezone.now()
            ai_run.save(update_fields=["status", "error_message", "completed_at"])
            emit_audit_event(
                request,
                event_type="ai.chat_prompt_failed",
                entity_type="ai_run",
                action="execute",
                entity_id=str(ai_run.pk),
                project_id=str(ai_run.project_id or ""),
                chat_id=str(ai_run.chat_id or ""),
                payload={"prompt_len": len(prompt or ""), "error": str(exc)},
            )

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


class AiChatCompletionsView(APIView):
    permission_classes = [IsAuthenticated]
    provider = OpenRouterProvider()

    def post(self, request):
        serializer = AiChatCompletionsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        self._enforce_rate_limits(request, data["thread_id"])

        chat = generics.get_object_or_404(Chat.objects.select_related("project"), pk=data["thread_id"])
        if not self._can_access_chat(request.user, chat):
            raise PermissionDenied("You do not have access to this thread.")
        emit_audit_event(
            request,
            event_type="ai.chat_completion_requested",
            entity_type="chat",
            action="request",
            entity_id=str(chat.pk),
            project_id=str(chat.project_id or ""),
            chat_id=str(chat.pk),
            payload={
                "context_type": data.get("context_type") or "",
                "context_id": str(data.get("context_id") or ""),
                "message_len": len(data["message"] or ""),
                "model_requested": str(data.get("model") or settings.DEFAULT_AI_MODEL),
            },
        )

        user_message = Message.objects.create(
            chat=chat,
            user=request.user,
            message_type=Message.TYPE_USER,
            content=data["message"],
            metadata={"source": "api.ai.chat.completions"},
        )

        model = data.get("model") or settings.DEFAULT_AI_MODEL
        max_tokens = int(settings.AI_CHAT_MAX_TOKENS)
        context_messages = self._build_context_messages(
            request=request,
            chat=chat,
            context_type=data.get("context_type"),
            context_id=data.get("context_id"),
        )
        history = list(
            Message.objects.filter(chat=chat)
            .exclude(pk=user_message.pk)
            .order_by("-created_at", "-id")[: int(settings.AI_CHAT_HISTORY_LIMIT)]
        )
        history.reverse()
        system_prompt = settings.AI_SYSTEM_PROMPT
        attachment_rows = list(
            ChatAttachment.objects.filter(chat=chat).order_by("-created_at", "-id")[:20]
        )
        if attachment_rows:
            names = "\n".join(
                f"- {a.title} ({a.document_type}, id=catt-{a.pk})" for a in reversed(attachment_rows)
            )
            system_prompt = (
                f"{system_prompt}\n\n"
                "Файлы, прикреплённые к этому чату (пользователь может ссылаться на них):\n"
                f"{names}"
            )
        llm_messages = [{"role": "system", "content": system_prompt}] + context_messages
        llm_messages.extend(self._message_to_llm(m) for m in history)
        llm_messages.append({"role": "user", "content": user_message.content})

        try:
            result = self.provider.chat_completions(messages=llm_messages, model=model, max_tokens=max_tokens)
        except RuntimeError as exc:
            emit_audit_event(
                request,
                event_type="ai.chat_completion_failed",
                entity_type="chat",
                action="provider_error",
                entity_id=str(chat.pk),
                project_id=str(chat.project_id or ""),
                chat_id=str(chat.pk),
                payload={"error": str(exc), "model": model},
            )
            user_message.delete()
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        assistant_message = Message.objects.create(
            chat=chat,
            user=None,
            message_type=Message.TYPE_ASSISTANT,
            content=result.text or "(empty response)",
            metadata={
                "provider": result.provider,
                "model": result.model,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "total_tokens": result.total_tokens,
                "cost_estimate": result.cost_estimate,
                "context_type": data.get("context_type"),
                "context_id": data.get("context_id"),
            },
        )
        emit_audit_event(
            request,
            event_type="ai.chat_completion_created",
            entity_type="chat_message",
            action="create",
            entity_id=str(assistant_message.pk),
            project_id=str(chat.project_id or ""),
            chat_id=str(chat.pk),
            payload={
                "provider": result.provider,
                "model": result.model,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "total_tokens": result.total_tokens,
                "cost_estimate": result.cost_estimate,
            },
        )
        return Response(
            {
                "thread_id": chat.pk,
                "message_id": assistant_message.pk,
                "provider": result.provider,
                "model": result.model,
                "output_text": assistant_message.content,
                "usage": {
                    "provider": result.provider,
                    "model": result.model,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "total_tokens": result.total_tokens,
                    "cost_estimate": result.cost_estimate,
                },
            },
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _message_to_llm(message: Message) -> dict:
        role_map = {
            Message.TYPE_SYSTEM: "system",
            Message.TYPE_ASSISTANT: "assistant",
            Message.TYPE_USER: "user",
        }
        return {"role": role_map.get(message.message_type, "user"), "content": message.content}

    @staticmethod
    def _can_access_chat(user, chat: Chat) -> bool:
        if not user or not user.is_authenticated:
            return False
        if chat.created_by_id == user.id:
            return True
        return chat.members.filter(user_id=user.id).exists()

    def _build_context_messages(self, *, request, chat: Chat, context_type: str | None, context_id: str | None):
        if not context_type:
            return []
        if not context_id:
            raise ValidationError({"context_id": "context_id is required when context_type is provided."})
        text = self._resolve_context_text(request=request, chat=chat, context_type=context_type, context_id=context_id)
        return [{"role": "system", "content": text}] if text else []

    def _resolve_context_text(self, *, request, chat: Chat, context_type: str, context_id: str) -> str:
        if context_type == "project":
            project = generics.get_object_or_404(Project, pk=context_id)
            return (
                f"Project context:\n"
                f"id={project.pk}\nname={project.name}\nstatus={project.status}\n"
                f"description={project.description or '-'}"
            )
        if context_type == "document":
            try:
                doc_id = int(str(context_id).split("-")[-1])
            except ValueError as exc:
                raise ValidationError({"context_id": "Invalid document id."}) from exc
            pdoc = ProjectDocument.objects.filter(pk=doc_id).select_related("project").first()
            if pdoc:
                return (
                    f"Project document context:\n"
                    f"id=pdoc-{pdoc.pk}\nproject_id={pdoc.project_id}\n"
                    f"title={pdoc.title}\ntype={pdoc.document_type}"
                )
            wdoc = WorkspaceCabinetDocument.objects.filter(pk=doc_id).first()
            if wdoc:
                return (
                    f"Workspace document context:\n"
                    f"id=doc-{wdoc.pk}\nowner_user_id={wdoc.user_id}\n"
                    f"title={wdoc.title}\ntype={wdoc.document_type}"
                )
            raise ValidationError({"context_id": "Document not found."})
        if context_type == "workspace":
            employee_id = workspace_data.resolve_employee_id_for_username(request.user.username)
            payload = workspace_data.get_employee_workspace(request, "employee")
            return (
                f"Workspace context:\n"
                f"employee_id={employee_id}\n"
                f"profile_name={(payload.get('profile') or {}).get('name', '')}\n"
                f"tasks_count={len(payload.get('tasks') or [])}\n"
                f"documents_count={len(payload.get('documents') or [])}"
            )
        if context_type == "task":
            # Tasks are currently sourced from workspace data; no dedicated DB model yet.
            employee_id = workspace_data.resolve_employee_id_for_username(request.user.username)
            task = workspace_data.get_workspace_task(employee_id, context_id)
            return (
                f"Task context:\n"
                f"id={task.get('id')}\ntitle={task.get('title')}\nstatus={task.get('status')}\n"
                f"project_id={task.get('project_id') or ''}\nsummary={task.get('summary') or ''}"
            )
        raise ValidationError({"context_type": f"Unsupported context_type '{context_type}'."})

    def _enforce_rate_limits(self, request, thread_id: int):
        user_limit = int(settings.AI_CHAT_RATE_LIMIT_USER_PER_MINUTE)
        org_limit = int(settings.AI_CHAT_RATE_LIMIT_COMPANY_PER_MINUTE)
        user_key = f"ai_chat_rl_user:{request.user.id}:{timezone.now().strftime('%Y%m%d%H%M')}"
        if self._increment_rate(user_key) > user_limit:
            emit_audit_event(
                request,
                event_type="ai.chat_rate_limited",
                entity_type="chat",
                action="deny",
                entity_id=str(thread_id),
                chat_id=str(thread_id),
                payload={"scope": "user", "limit": user_limit},
            )
            raise ValidationError({"detail": "Rate limit exceeded for user."})
        org_id = self._resolve_org_id(request.user, thread_id)
        if org_id:
            org_key = f"ai_chat_rl_org:{org_id}:{timezone.now().strftime('%Y%m%d%H%M')}"
            if self._increment_rate(org_key) > org_limit:
                emit_audit_event(
                    request,
                    event_type="ai.chat_rate_limited",
                    entity_type="chat",
                    action="deny",
                    entity_id=str(thread_id),
                    chat_id=str(thread_id),
                    payload={"scope": "company", "limit": org_limit, "organization_id": org_id},
                )
                raise ValidationError({"detail": "Rate limit exceeded for company."})

    @staticmethod
    def _increment_rate(key: str) -> int:
        added = cache.add(key, 1, timeout=70)
        if added:
            return 1
        try:
            return cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=70)
            return 1

    @staticmethod
    def _resolve_org_id(user, thread_id: int) -> int | None:
        org_id = (
            Chat.objects.filter(pk=thread_id).values_list("project__organization_id", flat=True).first()
        )
        if org_id:
            return int(org_id)
        membership = (
            OrganizationMember.objects.filter(user_id=user.id, is_active=True)
            .values_list("organization_id", flat=True)
            .first()
        )
        return int(membership) if membership else None
