from __future__ import annotations

from django.db import IntegrityError, transaction
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.service import emit_audit_event
from apps.core.api.pagination import offset_paginate
from apps.core.api.permissions import HasCapability, IsSuperAdmin, user_has_capability
from apps.identity.capabilities import STORAGE_QUOTAS_MANAGE, STORAGE_USAGE_VIEW_ALL
from apps.storage.models import StorageQuota
from apps.storage.quota_labels import build_storage_quota_source_label
from apps.storage.quota_usage import usage_bytes_for_quota
from apps.storage.service import compute_storage_usage


def _can_read_usage(user) -> bool:
    return user_has_capability(user, STORAGE_USAGE_VIEW_ALL) or user_has_capability(
        user, STORAGE_QUOTAS_MANAGE
    )


def _can_manage_quotas(user) -> bool:
    return user_has_capability(user, STORAGE_QUOTAS_MANAGE)


def _incoming_bytes_from_request(request) -> int | None:
    raw = (request.query_params.get("incoming_bytes") or "").strip()
    if not raw:
        return None
    try:
        v = int(raw, 10)
    except ValueError:
        return None
    if v < 0:
        return None
    return v


class StorageQuotaSerializer(serializers.ModelSerializer):
    scope_id = serializers.SerializerMethodField()
    remaining_bytes = serializers.SerializerMethodField()
    remaining_after_upload = serializers.SerializerMethodField()

    class Meta:
        model = StorageQuota
        fields = (
            "id",
            "scope",
            "scope_id",
            "source_label",
            "max_bytes",
            "warn_bytes",
            "is_active",
            "notes",
            "remaining_bytes",
            "remaining_after_upload",
            "created_at",
            "updated_at",
        )

    def get_scope_id(self, obj) -> str | None:
        return obj.scope_id or None

    def get_remaining_bytes(self, obj) -> int:
        usage = self.context.get("usage") or {}
        cur = usage_bytes_for_quota(obj, usage)
        return max(0, int(obj.max_bytes) - cur)

    def get_remaining_after_upload(self, obj) -> int | None:
        usage = self.context.get("usage") or {}
        incoming = self.context.get("incoming_bytes")
        if incoming is None:
            return None
        cur = usage_bytes_for_quota(obj, usage)
        return int(obj.max_bytes) - cur - int(incoming)


class StorageQuotaWriteSerializer(serializers.Serializer):
    scope = serializers.ChoiceField(choices=StorageQuota.Scope.choices)
    scope_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    source_label = serializers.CharField(required=False, allow_blank=True, max_length=255)
    max_bytes = serializers.IntegerField(min_value=1)
    warn_bytes = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    is_active = serializers.BooleanField(required=False, default=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class StorageQuotaPatchSerializer(serializers.Serializer):
    max_bytes = serializers.IntegerField(required=False, min_value=1)
    warn_bytes = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    is_active = serializers.BooleanField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    source_label = serializers.CharField(required=False, allow_blank=True, max_length=255)


class StorageUsageView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @extend_schema(
        operation_id="superAdminStorageUsage",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        if not _can_read_usage(request.user):
            return Response(
                {"code": "forbidden", "message": "Missing storage usage capability."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(compute_storage_usage())


class StorageQuotaListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @extend_schema(
        operation_id="superAdminStorageQuotasList",
        parameters=[
            OpenApiParameter("scope", OpenApiTypes.STR),
            OpenApiParameter("page", OpenApiTypes.INT),
            OpenApiParameter("page_size", OpenApiTypes.INT),
            OpenApiParameter(
                "incoming_bytes",
                OpenApiTypes.INT,
                description=(
                    "Optional hypothetical upload size; when set, each item includes "
                    "`remaining_after_upload` = max_bytes − current_usage − incoming_bytes."
                ),
            ),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        if not _can_read_usage(request.user):
            return Response(
                {"code": "forbidden", "message": "Missing storage capability."},
                status=status.HTTP_403_FORBIDDEN,
            )
        qs = StorageQuota.objects.all().order_by("scope", "scope_id")
        scope = (request.query_params.get("scope") or "").strip()
        if scope:
            qs = qs.filter(scope=scope)
        items, page, page_size, total = offset_paginate(qs, request)
        usage = compute_storage_usage()
        incoming = _incoming_bytes_from_request(request)
        ctx = {"usage": usage, "incoming_bytes": incoming}
        return Response(
            {
                "items": StorageQuotaSerializer(items, many=True, context=ctx).data,
                "page": page,
                "page_size": page_size,
                "total": total,
            }
        )

    @extend_schema(
        operation_id="superAdminStorageQuotasCreate",
        request=StorageQuotaWriteSerializer,
        responses={201: StorageQuotaSerializer},
    )
    def post(self, request):
        if not _can_manage_quotas(request.user):
            return Response(
                {"code": "forbidden", "message": "Missing storage.quotas.manage capability."},
                status=status.HTTP_403_FORBIDDEN,
            )
        ser = StorageQuotaWriteSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        scope = data["scope"]
        scope_id = (data.get("scope_id") or "").strip()
        if scope == StorageQuota.Scope.GLOBAL:
            scope_id = ""
        elif not scope_id:
            return Response(
                {
                    "code": "validation_error",
                    "message": "scope_id is required for non-global quotas.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        max_bytes = int(data["max_bytes"])
        warn = data.get("warn_bytes")
        source_label = (data.get("source_label") or "").strip()
        if not source_label:
            source_label = build_storage_quota_source_label(scope, scope_id)
        if warn is not None and int(warn) > max_bytes:
            return Response(
                {
                    "code": "validation_error",
                    "message": "warn_bytes cannot exceed max_bytes.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with transaction.atomic():
                obj = StorageQuota.objects.create(
                    scope=scope,
                    scope_id=scope_id,
                    source_label=source_label,
                    max_bytes=max_bytes,
                    warn_bytes=warn,
                    is_active=data.get("is_active", True),
                    notes=(data.get("notes") or "").strip(),
                )
        except IntegrityError:
            return Response(
                {
                    "code": "conflict",
                    "message": "Quota for this scope already exists.",
                    "details": {"scope": scope, "scope_id": scope_id or None},
                },
                status=status.HTTP_409_CONFLICT,
            )
        emit_audit_event(
            request,
            event_type="storage.quota.created",
            entity_type="storage_quota",
            entity_id=str(obj.id),
            action="create_quota",
            payload={"scope": scope, "scope_id": scope_id or None, "max_bytes": max_bytes},
        )
        usage = compute_storage_usage()
        return Response(
            StorageQuotaSerializer(obj, context={"usage": usage, "incoming_bytes": None}).data,
            status=status.HTTP_201_CREATED,
        )


class StorageQuotaDetailView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin, HasCapability]
    required_capability = STORAGE_QUOTAS_MANAGE

    @staticmethod
    def _get(quota_id: int):
        try:
            return StorageQuota.objects.get(pk=quota_id)
        except StorageQuota.DoesNotExist:
            return None

    @extend_schema(
        operation_id="superAdminStorageQuotasUpdate",
        request=StorageQuotaPatchSerializer,
        responses={200: StorageQuotaSerializer},
    )
    def patch(self, request, quota_id: int):
        obj = self._get(quota_id)
        if not obj:
            return Response({"detail": "Quota not found."}, status=status.HTTP_404_NOT_FOUND)
        ser = StorageQuotaPatchSerializer(data=request.data or {}, partial=True)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if "max_bytes" in data:
            obj.max_bytes = int(data["max_bytes"])
        if "warn_bytes" in data:
            obj.warn_bytes = data["warn_bytes"]
        if "is_active" in data:
            obj.is_active = data["is_active"]
        if "notes" in data:
            obj.notes = (data.get("notes") or "").strip()
        if "source_label" in data:
            obj.source_label = (data.get("source_label") or "").strip()
        if not (obj.source_label or "").strip():
            obj.source_label = build_storage_quota_source_label(obj.scope, obj.scope_id or "")
        if obj.warn_bytes is not None and obj.warn_bytes > obj.max_bytes:
            return Response(
                {"code": "validation_error", "message": "warn_bytes cannot exceed max_bytes."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj.save()
        emit_audit_event(
            request,
            event_type="storage.quota.updated",
            entity_type="storage_quota",
            entity_id=str(obj.id),
            action="update_quota",
            payload={"scope": obj.scope, "scope_id": obj.scope_id or None, "max_bytes": obj.max_bytes},
        )
        usage = compute_storage_usage()
        return Response(StorageQuotaSerializer(obj, context={"usage": usage, "incoming_bytes": None}).data)

    @extend_schema(
        operation_id="superAdminStorageQuotasDelete",
        responses={204: None},
    )
    def delete(self, request, quota_id: int):
        obj = self._get(quota_id)
        if not obj:
            return Response({"detail": "Quota not found."}, status=status.HTTP_404_NOT_FOUND)
        pk = str(obj.id)
        scope = obj.scope
        sid = obj.scope_id
        obj.delete()
        emit_audit_event(
            request,
            event_type="storage.quota.deleted",
            entity_type="storage_quota",
            entity_id=pk,
            action="delete_quota",
            payload={"scope": scope, "scope_id": sid or None},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
