from __future__ import annotations

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
from apps.identity.capabilities import STORAGE_PROVIDERS_MANAGE
from apps.storage.credentials_vault import (
    credentials_blob_has_secret,
    decrypt_credentials_field,
    encrypt_credentials_field,
)
from apps.storage.default_policy import repair_storage_provider_defaults
from apps.storage.models import StorageProvider
from apps.storage.s3_probe import probe_s3_compatible_storage


def _clear_other_defaults(exclude_pk: int | None) -> None:
    qs = StorageProvider.objects.filter(is_default=True)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    qs.update(is_default=False)


class StorageProviderSerializer(serializers.ModelSerializer):
    has_secret = serializers.SerializerMethodField()

    class Meta:
        model = StorageProvider
        fields = (
            "id",
            "code",
            "name",
            "kind",
            "is_active",
            "is_default",
            "priority",
            "endpoint_url",
            "bucket",
            "region",
            "use_ssl",
            "path_style",
            "has_secret",
            "created_at",
            "updated_at",
        )

    def get_has_secret(self, obj) -> bool:
        return credentials_blob_has_secret(obj.credentials)


class StorageProviderWriteSerializer(serializers.Serializer):
    code = serializers.RegexField(regex=r"^[a-z0-9_-]+$", required=False, max_length=32)
    name = serializers.CharField(max_length=128, required=False)
    kind = serializers.ChoiceField(choices=StorageProvider.Kind.choices, required=False)
    is_active = serializers.BooleanField(required=False)
    is_default = serializers.BooleanField(required=False)
    priority = serializers.IntegerField(required=False)
    endpoint_url = serializers.CharField(required=False, allow_blank=True, max_length=512)
    bucket = serializers.CharField(required=False, allow_blank=True, max_length=255)
    region = serializers.CharField(required=False, allow_blank=True, max_length=64)
    use_ssl = serializers.BooleanField(required=False)
    path_style = serializers.BooleanField(required=False)
    access_key = serializers.CharField(required=False, allow_blank=True, max_length=256)
    secret_key = serializers.CharField(required=False, allow_blank=True, max_length=512)


class StorageProviderProbeResultSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    latency_ms = serializers.IntegerField()
    message = serializers.CharField()
    provider_code = serializers.CharField()


class SuperAdminStorageProvidersListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin, HasCapability]
    required_capability = STORAGE_PROVIDERS_MANAGE

    @extend_schema(
        operation_id="superAdminStorageProvidersList",
        parameters=[
            OpenApiParameter("search", OpenApiTypes.STR),
            OpenApiParameter("is_active", OpenApiTypes.BOOL),
            OpenApiParameter("page", OpenApiTypes.INT),
            OpenApiParameter("page_size", OpenApiTypes.INT),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        qs = StorageProvider.objects.all().order_by("priority", "code")
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(Q(code__icontains=search) | Q(name__icontains=search) | Q(bucket__icontains=search))

        is_active_raw = request.query_params.get("is_active")
        if is_active_raw is not None:
            val = str(is_active_raw).strip().lower()
            if val in {"true", "1", "yes"}:
                qs = qs.filter(is_active=True)
            elif val in {"false", "0", "no"}:
                qs = qs.filter(is_active=False)

        items, page, page_size, total = offset_paginate(qs, request)
        return Response(
            {
                "items": StorageProviderSerializer(items, many=True).data,
                "page": page,
                "page_size": page_size,
                "total": total,
            }
        )

    @extend_schema(
        operation_id="superAdminStorageProvidersCreate",
        request=StorageProviderWriteSerializer,
        responses={201: StorageProviderSerializer},
    )
    def post(self, request):
        serializer = StorageProviderWriteSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        code = (payload.get("code") or "").strip().lower()
        name = (payload.get("name") or "").strip()
        bucket = (payload.get("bucket") or "").strip()
        if not code or not name or not bucket:
            return Response(
                {
                    "code": "validation_error",
                    "message": "Fields `code`, `name`, and `bucket` are required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        access_key = (payload.get("access_key") or "").strip()
        secret_key = (payload.get("secret_key") or "").strip()
        if not access_key or not secret_key:
            return Response(
                {
                    "code": "validation_error",
                    "message": "Fields `access_key` and `secret_key` are required on create.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        kind = payload.get("kind") or StorageProvider.Kind.S3_COMPAT
        is_default = bool(payload.get("is_default", False))

        try:
            with transaction.atomic():
                if is_default:
                    _clear_other_defaults(None)
                obj = StorageProvider.objects.create(
                    code=code,
                    name=name,
                    kind=kind,
                    is_active=payload.get("is_active", True),
                    is_default=is_default,
                    priority=payload.get("priority", 100),
                    endpoint_url=(payload.get("endpoint_url") or "").strip(),
                    bucket=bucket,
                    region=(payload.get("region") or "").strip(),
                    use_ssl=payload.get("use_ssl", True),
                    path_style=payload.get("path_style", True),
                    credentials=encrypt_credentials_field(access_key, secret_key),
                )
        except IntegrityError as exc:
            err = str(exc).lower()
            if "uniq_storage_provider_single_default" in err or "is_default" in err:
                return Response(
                    {"code": "conflict", "message": "Another default storage provider already exists."},
                    status=status.HTTP_409_CONFLICT,
                )
            return Response(
                {"code": "conflict", "message": "Provider code already exists.", "details": {"code": code}},
                status=status.HTTP_409_CONFLICT,
            )

        emit_audit_event(
            request,
            event_type="storage.provider.created",
            entity_type="storage_provider",
            entity_id=str(obj.id),
            action="create_storage_provider",
            payload={
                "code": obj.code,
                "kind": obj.kind,
                "bucket": obj.bucket,
                "is_default": obj.is_default,
                "has_endpoint": bool(obj.endpoint_url),
            },
        )
        repair_storage_provider_defaults()
        return Response(StorageProviderSerializer(obj).data, status=status.HTTP_201_CREATED)


class SuperAdminStorageProviderDetailView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin, HasCapability]
    required_capability = STORAGE_PROVIDERS_MANAGE

    @staticmethod
    def _get(provider_id: int):
        try:
            return StorageProvider.objects.get(pk=provider_id)
        except StorageProvider.DoesNotExist:
            return None

    @extend_schema(
        operation_id="superAdminStorageProvidersUpdate",
        request=StorageProviderWriteSerializer,
        responses={200: StorageProviderSerializer},
    )
    def patch(self, request, provider_id: int):
        provider = self._get(provider_id)
        if not provider:
            return Response({"detail": "Provider not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = StorageProviderWriteSerializer(data=request.data or {}, partial=True)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        updates: set[str] = set()
        audit_changes: dict[str, object] = {}

        if "code" in payload:
            code = payload["code"].strip().lower()
            if code != provider.code:
                provider.code = code
                updates.add("code")
                audit_changes["code"] = code
        if "name" in payload:
            name = payload["name"].strip()
            if name != provider.name:
                provider.name = name
                updates.add("name")
                audit_changes["name"] = name
        if "kind" in payload and payload["kind"] != provider.kind:
            provider.kind = payload["kind"]
            updates.add("kind")
            audit_changes["kind"] = provider.kind
        if "is_active" in payload and payload["is_active"] != provider.is_active:
            provider.is_active = payload["is_active"]
            updates.add("is_active")
            audit_changes["is_active"] = provider.is_active
        if "priority" in payload and payload["priority"] != provider.priority:
            provider.priority = payload["priority"]
            updates.add("priority")
            audit_changes["priority"] = provider.priority
        if "endpoint_url" in payload:
            ep = (payload["endpoint_url"] or "").strip()
            if ep != provider.endpoint_url:
                provider.endpoint_url = ep
                updates.add("endpoint_url")
                audit_changes["has_endpoint"] = bool(ep)
        if "bucket" in payload:
            bucket = (payload["bucket"] or "").strip()
            if bucket != provider.bucket:
                provider.bucket = bucket
                updates.add("bucket")
                audit_changes["bucket"] = bucket
        if "region" in payload:
            reg = (payload["region"] or "").strip()
            if reg != provider.region:
                provider.region = reg
                updates.add("region")
        if "use_ssl" in payload and payload["use_ssl"] != provider.use_ssl:
            provider.use_ssl = payload["use_ssl"]
            updates.add("use_ssl")
        if "path_style" in payload and payload["path_style"] != provider.path_style:
            provider.path_style = payload["path_style"]
            updates.add("path_style")

        if "is_default" in payload:
            want_default = bool(payload["is_default"])
            if want_default != provider.is_default:
                provider.is_default = want_default
                updates.add("is_default")
                audit_changes["is_default"] = want_default

        plain = decrypt_credentials_field(provider.credentials)
        secret_touched = False
        if "access_key" in payload:
            ak = (payload["access_key"] or "").strip()
            if ak != plain["access_key"]:
                plain["access_key"] = ak
                secret_touched = True
        if "secret_key" in payload:
            sk = (payload["secret_key"] or "").strip()
            if sk != plain["secret_key"]:
                plain["secret_key"] = sk
                secret_touched = True

        if secret_touched:
            provider.credentials = encrypt_credentials_field(plain["access_key"], plain["secret_key"])
            updates.add("credentials")
            emit_audit_event(
                request,
                event_type="storage.provider.secret_rotated",
                entity_type="storage_provider",
                entity_id=str(provider.id),
                action="rotate_storage_credentials",
                payload={"code": provider.code, "has_secret": bool(plain.get("secret_key"))},
            )

        if not updates:
            repair_storage_provider_defaults()
            return Response(StorageProviderSerializer(provider).data)

        try:
            with transaction.atomic():
                if provider.is_default:
                    _clear_other_defaults(provider.pk)
                provider.save()
        except IntegrityError as exc:
            err = str(exc).lower()
            if "uniq_storage_provider_single_default" in err:
                return Response(
                    {"code": "conflict", "message": "Another default storage provider already exists."},
                    status=status.HTTP_409_CONFLICT,
                )
            if "unique" in err or "uniq" in err:
                return Response(
                    {"code": "conflict", "message": "Provider code already exists.", "details": {"code": provider.code}},
                    status=status.HTTP_409_CONFLICT,
                )
            raise

        emit_audit_event(
            request,
            event_type="storage.provider.updated",
            entity_type="storage_provider",
            entity_id=str(provider.id),
            action="update_storage_provider",
            payload=audit_changes,
        )
        repair_storage_provider_defaults()
        return Response(StorageProviderSerializer(provider).data)

    @extend_schema(
        operation_id="superAdminStorageProvidersDelete",
        responses={204: None},
    )
    def delete(self, request, provider_id: int):
        provider = self._get(provider_id)
        if not provider:
            return Response({"detail": "Provider not found."}, status=status.HTTP_404_NOT_FOUND)

        pk = str(provider.id)
        code = provider.code
        was_default = provider.is_default
        provider.delete()
        if was_default:
            # Leave platform without explicit default until another is promoted.
            pass
        emit_audit_event(
            request,
            event_type="storage.provider.deleted",
            entity_type="storage_provider",
            entity_id=pk,
            action="delete_storage_provider",
            payload={"code": code},
        )
        repair_storage_provider_defaults()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SuperAdminStorageProviderProbeView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin, HasCapability]
    required_capability = STORAGE_PROVIDERS_MANAGE

    @extend_schema(
        operation_id="superAdminStorageProvidersProbe",
        responses={200: StorageProviderProbeResultSerializer},
    )
    def post(self, request, provider_id: int):
        try:
            provider = StorageProvider.objects.get(pk=provider_id)
        except StorageProvider.DoesNotExist:
            return Response({"detail": "Provider not found."}, status=status.HTTP_404_NOT_FOUND)

        if provider.kind != StorageProvider.Kind.S3_COMPAT:
            return Response(
                {
                    "code": "validation_error",
                    "message": f"Probe not implemented for kind '{provider.kind}'.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        c = decrypt_credentials_field(provider.credentials)
        access = (c.get("access_key") or "").strip()
        secret = (c.get("secret_key") or "").strip()
        result = probe_s3_compatible_storage(
            endpoint_url=provider.endpoint_url or None,
            bucket=provider.bucket,
            region=provider.region or None,
            use_ssl=provider.use_ssl,
            path_style=provider.path_style,
            access_key=access,
            secret_key=secret,
        )
        emit_audit_event(
            request,
            event_type="storage.provider.probed",
            entity_type="storage_provider",
            entity_id=str(provider.id),
            action="probe_storage_provider",
            payload={
                "ok": result["ok"],
                "latency_ms": result["latency_ms"],
                "code": provider.code,
            },
        )
        return Response(
            {
                "ok": result["ok"],
                "latency_ms": result["latency_ms"],
                "message": result["message"],
                "provider_code": provider.code,
            }
        )
