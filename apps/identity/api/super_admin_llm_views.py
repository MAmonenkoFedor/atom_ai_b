from __future__ import annotations

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.service import emit_audit_event
from apps.core.api.pagination import offset_paginate
from apps.core.api.permissions import HasCapability, IsSuperAdmin
from apps.identity.capabilities import LLM_PROVIDERS_MANAGE
from apps.llm_gateway.models import LlmModel, LlmProvider
from apps.llm_gateway.services import LlmGatewayService


class LlmProviderSerializer(serializers.ModelSerializer):
    has_secret = serializers.SerializerMethodField()
    base_url_override = serializers.SerializerMethodField()

    class Meta:
        model = LlmProvider
        fields = (
            "id",
            "code",
            "name",
            "is_active",
            "priority",
            "mock_override",
            "has_secret",
            "base_url_override",
            "created_at",
        )

    @staticmethod
    def _config(provider) -> dict:
        return provider.config if isinstance(provider.config, dict) else {}

    def get_has_secret(self, obj) -> bool:
        config = self._config(obj)
        return bool((config.get("api_key") or "").strip())

    def get_base_url_override(self, obj) -> str | None:
        config = self._config(obj)
        base_url = (config.get("base_url") or "").strip()
        return base_url or None


class LlmProviderUpsertSerializer(serializers.Serializer):
    code = serializers.RegexField(regex=r"^[a-z0-9_-]+$", required=False, max_length=32)
    name = serializers.CharField(max_length=128, required=False)
    is_active = serializers.BooleanField(required=False)
    priority = serializers.IntegerField(required=False)
    mock_override = serializers.BooleanField(required=False, allow_null=True)
    base_url_override = serializers.CharField(required=False, allow_blank=True, max_length=255)
    api_key = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True, max_length=512)


class LlmProviderProbeResultSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    mock = serializers.BooleanField()
    provider_code = serializers.CharField()
    model_code = serializers.CharField()
    latency_ms = serializers.IntegerField()
    message = serializers.CharField()


class SuperAdminLlmProvidersListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin, HasCapability]
    required_capability = LLM_PROVIDERS_MANAGE

    @extend_schema(
        operation_id="superAdminLlmProvidersList",
        parameters=[
            OpenApiParameter("search", OpenApiTypes.STR),
            OpenApiParameter("is_active", OpenApiTypes.BOOL),
            OpenApiParameter("page", OpenApiTypes.INT),
            OpenApiParameter("page_size", OpenApiTypes.INT),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        qs = LlmProvider.objects.all().order_by("priority", "code")
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(Q(code__icontains=search) | Q(name__icontains=search))

        is_active_raw = request.query_params.get("is_active")
        if is_active_raw is not None:
            val = str(is_active_raw).strip().lower()
            if val in {"true", "1", "yes"}:
                qs = qs.filter(is_active=True)
            elif val in {"false", "0", "no"}:
                qs = qs.filter(is_active=False)

        items, page, page_size, total = offset_paginate(qs, request)
        data = LlmProviderSerializer(items, many=True).data
        return Response({"items": data, "page": page, "page_size": page_size, "total": total})

    @extend_schema(
        operation_id="superAdminLlmProvidersCreate",
        request=LlmProviderUpsertSerializer,
        responses={201: LlmProviderSerializer},
    )
    def post(self, request):
        serializer = LlmProviderUpsertSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        code = (payload.get("code") or "").strip().lower()
        name = (payload.get("name") or "").strip()
        if not code or not name:
            return Response(
                {
                    "code": "validation_error",
                    "message": "Fields `code` and `name` are required.",
                    "details": {"code_required": not bool(code), "name_required": not bool(name)},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            provider = LlmProvider(
                code=code,
                name=name,
                is_active=payload.get("is_active", True),
                priority=payload.get("priority", 100),
                mock_override=payload.get("mock_override"),
                config={},
            )
            base_url = (payload.get("base_url_override") or "").strip()
            api_key = (payload.get("api_key") or "").strip()
            if base_url:
                provider.config["base_url"] = base_url
            if api_key:
                provider.config["api_key"] = api_key
            try:
                provider.save()
            except IntegrityError:
                return Response(
                    {
                        "code": "conflict",
                        "message": "Provider code already exists.",
                        "details": {"code": code},
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        emit_audit_event(
            request,
            event_type="llm.provider.created",
            entity_type="llm_provider",
            entity_id=str(provider.id),
            action="create_provider",
            payload={
                "code": provider.code,
                "name": provider.name,
                "is_active": provider.is_active,
                "priority": provider.priority,
                "mock_override": provider.mock_override,
                "has_secret": bool(api_key),
                "has_base_url_override": bool(base_url),
            },
        )
        return Response(LlmProviderSerializer(provider).data, status=status.HTTP_201_CREATED)


class SuperAdminLlmProviderDetailView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin, HasCapability]
    required_capability = LLM_PROVIDERS_MANAGE

    @staticmethod
    def _get_provider(provider_id: int):
        try:
            return LlmProvider.objects.get(pk=provider_id)
        except LlmProvider.DoesNotExist:
            return None

    @extend_schema(
        operation_id="superAdminLlmProvidersUpdate",
        request=LlmProviderUpsertSerializer,
        responses={200: LlmProviderSerializer},
    )
    def patch(self, request, provider_id: int):
        provider = self._get_provider(provider_id)
        if not provider:
            return Response({"detail": "Provider not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = LlmProviderUpsertSerializer(data=request.data or {}, partial=True)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        updates: list[str] = []
        audit_changes: dict[str, object] = {}

        if "code" in payload:
            code = payload["code"].strip().lower()
            if code != provider.code:
                provider.code = code
                updates.append("code")
                audit_changes["code"] = code
        if "name" in payload:
            name = payload["name"].strip()
            if name != provider.name:
                provider.name = name
                updates.append("name")
                audit_changes["name"] = name
        if "is_active" in payload and payload["is_active"] != provider.is_active:
            provider.is_active = payload["is_active"]
            updates.append("is_active")
            audit_changes["is_active"] = provider.is_active
        if "priority" in payload and payload["priority"] != provider.priority:
            provider.priority = payload["priority"]
            updates.append("priority")
            audit_changes["priority"] = provider.priority
        if "mock_override" in payload and payload["mock_override"] != provider.mock_override:
            provider.mock_override = payload["mock_override"]
            updates.append("mock_override")
            audit_changes["mock_override"] = provider.mock_override

        config = provider.config if isinstance(provider.config, dict) else {}
        if "base_url_override" in payload:
            base_url = (payload["base_url_override"] or "").strip()
            if base_url:
                config["base_url"] = base_url
            else:
                config.pop("base_url", None)
            audit_changes["has_base_url_override"] = bool(base_url)
        if "api_key" in payload:
            api_key = (payload["api_key"] or "").strip()
            if api_key:
                config["api_key"] = api_key
            else:
                config.pop("api_key", None)
            audit_changes["has_secret"] = bool(api_key)
            emit_audit_event(
                request,
                event_type="llm.provider.secret_rotated",
                entity_type="llm_provider",
                entity_id=str(provider.id),
                action="rotate_provider_secret",
                payload={"code": provider.code, "has_secret": bool(api_key)},
            )
        provider.config = config
        if "base_url_override" in payload or "api_key" in payload:
            updates.append("config")

        if not updates:
            return Response(LlmProviderSerializer(provider).data)

        try:
            provider.save(update_fields=tuple(dict.fromkeys(updates)))
        except IntegrityError:
            return Response(
                {
                    "code": "conflict",
                    "message": "Provider code already exists.",
                    "details": {"code": provider.code},
                },
                status=status.HTTP_409_CONFLICT,
            )

        emit_audit_event(
            request,
            event_type="llm.provider.updated",
            entity_type="llm_provider",
            entity_id=str(provider.id),
            action="update_provider",
            payload=audit_changes,
        )
        return Response(LlmProviderSerializer(provider).data)

    @extend_schema(
        operation_id="superAdminLlmProvidersDelete",
        responses={204: None},
    )
    def delete(self, request, provider_id: int):
        provider = self._get_provider(provider_id)
        if not provider:
            return Response({"detail": "Provider not found."}, status=status.HTTP_404_NOT_FOUND)

        active_models = list(
            LlmModel.objects.filter(provider=provider, is_active=True).values_list("code", flat=True)
        )
        if active_models:
            return Response(
                {
                    "code": "conflict",
                    "message": "Cannot delete provider with active models.",
                    "details": {"active_models": active_models},
                },
                status=status.HTTP_409_CONFLICT,
            )

        provider_id_str = str(provider.id)
        provider_code = provider.code
        provider.delete()
        emit_audit_event(
            request,
            event_type="llm.provider.deleted",
            entity_type="llm_provider",
            entity_id=provider_id_str,
            action="delete_provider",
            payload={"code": provider_code},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class SuperAdminLlmProviderProbeView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin, HasCapability]
    required_capability = LLM_PROVIDERS_MANAGE

    @extend_schema(
        operation_id="superAdminLlmProvidersProbe",
        responses={200: LlmProviderProbeResultSerializer},
    )
    def post(self, request, provider_id: int):
        try:
            provider = LlmProvider.objects.get(pk=provider_id)
        except LlmProvider.DoesNotExist:
            return Response({"detail": "Provider not found."}, status=status.HTTP_404_NOT_FOUND)

        model = (
            LlmModel.objects.filter(provider=provider, is_active=True)
            .order_by("code")
            .first()
        )
        if not model:
            return Response(
                {
                    "code": "validation_error",
                    "message": "Provider has no active models to probe.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        adapter = LlmGatewayService.ADAPTERS.get(provider.code)
        if not adapter:
            return Response(
                {
                    "code": "not_found",
                    "message": f"No adapter registered for provider '{provider.code}'.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            result = adapter.generate(
                prompt="health_check",
                model_code=model.code,
                provider=provider,
            )
        except Exception as exc:
            emit_audit_event(
                request,
                event_type="llm.provider.probed",
                entity_type="llm_provider",
                entity_id=str(provider.id),
                action="probe_provider",
                payload={"ok": False, "error": str(exc), "model_code": model.code},
            )
            return Response(
                {
                    "ok": False,
                    "mock": bool(provider.mock_override is True),
                    "provider_code": provider.code,
                    "model_code": model.code,
                    "latency_ms": 0,
                    "message": str(exc),
                }
            )

        mock_enabled = (
            provider.mock_override
            if provider.mock_override is not None
            else bool(settings.LLM_GATEWAY_MOCK_MODE)
        )
        emit_audit_event(
            request,
            event_type="llm.provider.probed",
            entity_type="llm_provider",
            entity_id=str(provider.id),
            action="probe_provider",
            payload={"ok": True, "model_code": model.code, "mock": mock_enabled},
        )
        return Response(
            {
                "ok": True,
                "mock": mock_enabled,
                "provider_code": provider.code,
                "model_code": model.code,
                "latency_ms": 0,
                "message": result.text[:200] or "Probe ok",
            }
        )
