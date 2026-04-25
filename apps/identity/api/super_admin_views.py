"""Super-admin endpoints for global participant and capability management.

Endpoints prefix: ``/api/v1/super-admin/...``

Contract source: ``docs/SUPER_ADMIN_CABINET_PM_PLAN.md`` section 15.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import serializers, status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.service import emit_audit_event
from apps.core.api.permissions import (
    HasCapability,
    IsSuperAdmin,
    effective_capabilities,
)
from apps.identity.capabilities import (
    ALL_CAPABILITIES,
    AUDIT_VIEW_ALL,
    CAPABILITIES_MANAGE,
    ROLES_MANAGE,
    USERS_DISABLE,
    USERS_ENABLE,
    USERS_FORCE_LOGOUT,
    USERS_INVITE,
    USERS_VIEW_ALL,
    capabilities_for_roles,
    is_known_capability,
)
from apps.identity.models import Role, UserCapability, UserRole

User = get_user_model()


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _role_codes_for(user) -> list[str]:
    return sorted(
        {
            assignment.role.code
            for assignment in user.role_assignments.select_related("role").all()
            if assignment.role
        }
    )


def _organization_ids_for(user) -> list[str]:
    return sorted(
        {
            str(assignment.organization_id)
            for assignment in user.role_assignments.all()
            if assignment.organization_id
        }
    )


def _normalize_role(code: str) -> str:
    if code == "admin":
        return "company_admin"
    if code in {"ceo", "executive"}:
        return "executive"
    return code


def _is_super_admin_user(user) -> bool:
    """True iff the user currently holds the ``super_admin`` role."""

    return "super_admin" in _role_codes_for(user)


def _ceo_forbidden_response(message: str) -> Response:
    return Response(
        {"code": "forbidden_ceo", "message": message},
        status=status.HTTP_403_FORBIDDEN,
    )


class PlatformUserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()
    org_ids = serializers.SerializerMethodField()
    last_seen_at = serializers.DateTimeField(source="last_login", allow_null=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "username",
            "full_name",
            "status",
            "roles",
            "org_ids",
            "last_seen_at",
            "date_joined",
        )

    def get_full_name(self, obj) -> str:
        return obj.get_full_name().strip() or obj.username

    def get_status(self, obj) -> str:
        return "active" if obj.is_active else "disabled"

    def get_roles(self, obj) -> list[str]:
        return sorted({_normalize_role(code) for code in _role_codes_for(obj)})

    def get_org_ids(self, obj) -> list[str]:
        return _organization_ids_for(obj)


class PlatformUserDetailSerializer(PlatformUserSerializer):
    capabilities = serializers.SerializerMethodField()
    explicit_capabilities = serializers.SerializerMethodField()

    class Meta(PlatformUserSerializer.Meta):
        fields = PlatformUserSerializer.Meta.fields + (
            "capabilities",
            "explicit_capabilities",
        )

    def get_capabilities(self, obj) -> list[str]:
        return sorted(effective_capabilities(obj))

    def get_explicit_capabilities(self, obj) -> list[dict]:
        return [
            {
                "capability": grant.capability,
                "scope": grant.scope,
                "reason": grant.reason,
                "granted_at": grant.created_at.isoformat(),
            }
            for grant in obj.capability_grants.all().order_by("capability", "scope")
        ]


class DisableUserInputSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class InviteUserInputSerializer(serializers.Serializer):
    """Internal v1: create a user with email, login (= local part of email), and password."""

    email = serializers.EmailField()
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=128, write_only=True, min_length=8)
    full_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    initial_roles = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
        allow_empty=True,
        default=list,
    )
    org_ids = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
        allow_empty=True,
        default=list,
    )

    def validate(self, attrs):
        email = attrs["email"].strip().lower()
        username = attrs["username"].strip()
        password = attrs["password"]
        if "@" not in email:
            raise serializers.ValidationError({"email": "Некорректный адрес почты."})
        local_part = email.split("@", 1)[0]
        if username.lower() != local_part.lower():
            raise serializers.ValidationError(
                {
                    "username": "Логин должен совпадать с частью адреса до символа @ "
                    "(без учёта регистра)."
                }
            )
        attrs["email"] = email
        attrs["username"] = username
        dummy = User(username=username, email=email)
        try:
            validate_password(password, dummy)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs


class SetUserPasswordInputSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=128, write_only=True, min_length=8)


class UpdateRolesInputSerializer(serializers.Serializer):
    roles = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=True,
        allow_empty=True,
    )
    scope = serializers.CharField(max_length=128, required=False, default="global")
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class UpdateCapabilitiesInputSerializer(serializers.Serializer):
    capabilities_add = serializers.ListField(
        child=serializers.CharField(max_length=128), required=False, default=list
    )
    capabilities_remove = serializers.ListField(
        child=serializers.CharField(max_length=128), required=False, default=list
    )
    scope = serializers.CharField(max_length=128, required=False, default="global")
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_scope_organization_id(scope: str) -> str | None:
    if not scope or scope == "global":
        return None
    if scope.startswith("org:"):
        return scope.split(":", 1)[1] or None
    return None


def _paginate(queryset, request):
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(request.query_params.get("page_size", 25))
    except (TypeError, ValueError):
        page_size = 25
    page_size = max(1, min(page_size, 100))

    total = queryset.count()
    start = (page - 1) * page_size
    end = start + page_size
    items = list(queryset[start:end])
    return items, page, page_size, total


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class PlatformUsersListView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin, HasCapability]
    required_capability = USERS_VIEW_ALL

    @extend_schema(
        operation_id="superAdminUsersList",
        parameters=[
            OpenApiParameter("search", OpenApiTypes.STR),
            OpenApiParameter("status", OpenApiTypes.STR),
            OpenApiParameter("role", OpenApiTypes.STR),
            OpenApiParameter("org_id", OpenApiTypes.STR),
            OpenApiParameter("page", OpenApiTypes.INT),
            OpenApiParameter("page_size", OpenApiTypes.INT),
        ],
        responses=PlatformUserSerializer(many=True),
    )
    def get(self, request):
        qs = (
            User.objects.all()
            .prefetch_related("role_assignments__role")
            .order_by("-date_joined", "id")
        )

        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(email__icontains=search)
                | Q(username__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )

        user_status = (request.query_params.get("status") or "").strip()
        if user_status == "active":
            qs = qs.filter(is_active=True)
        elif user_status == "disabled":
            qs = qs.filter(is_active=False)

        role = (request.query_params.get("role") or "").strip()
        if role:
            qs = qs.filter(role_assignments__role__code=role).distinct()

        org_id = (request.query_params.get("org_id") or "").strip()
        if org_id:
            qs = qs.filter(role_assignments__organization_id=org_id).distinct()

        items, page, page_size, total = _paginate(qs, request)
        data = PlatformUserSerializer(items, many=True).data
        return Response(
            {
                "items": data,
                "page": page,
                "page_size": page_size,
                "total": total,
            }
        )


class PlatformUserDetailView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin, HasCapability]
    required_capability = USERS_VIEW_ALL

    @extend_schema(
        operation_id="superAdminUsersDetail",
        responses=PlatformUserDetailSerializer,
    )
    def get(self, request, user_id: int):
        try:
            user = (
                User.objects.prefetch_related("role_assignments__role")
                .prefetch_related("capability_grants")
                .get(pk=user_id)
            )
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(PlatformUserDetailSerializer(user).data)


class InviteUserView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin, HasCapability]
    required_capability = USERS_INVITE

    @extend_schema(
        operation_id="superAdminUsersInvite",
        request=InviteUserInputSerializer,
        responses={201: PlatformUserSerializer},
    )
    def post(self, request):
        serializer = InviteUserInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        email = payload["email"]
        username = payload["username"].strip()
        password = payload["password"]
        full_name = (payload.get("full_name") or "").strip()

        if User.objects.filter(Q(email__iexact=email) | Q(username__iexact=username)).exists():
            return Response(
                {
                    "code": "conflict",
                    "message": "Пользователь с такой почтой или логином уже существует.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=full_name[:150] if full_name else "",
                is_active=True,
            )
            for role_code in payload.get("initial_roles", []) or []:
                role = Role.objects.filter(code=role_code).first()
                if role:
                    UserRole.objects.get_or_create(user=user, role=role, organization=None)

        emit_audit_event(
            request,
            event_type="user.created",
            entity_type="user",
            entity_id=str(user.id),
            action="create",
            payload={
                "email": email,
                "username": username,
                "initial_roles": payload.get("initial_roles", []),
                "org_ids": payload.get("org_ids", []),
            },
        )

        return Response(PlatformUserSerializer(user).data, status=status.HTTP_201_CREATED)


class SetUserPasswordView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin, HasCapability]
    required_capability = USERS_INVITE

    @extend_schema(
        operation_id="superAdminUsersSetPassword",
        request=SetUserPasswordInputSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, user_id: int):
        if user_id == request.user.id:
            return Response(
                {
                    "code": "forbidden",
                    "message": "Смена пароля для своей учётной записи через эту форму недоступна.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        if _is_super_admin_user(user) and user.id != request.user.id:
            return _ceo_forbidden_response(
                "Пароль суперадмина (CEO) может менять только он сам через свой кабинет."
            )

        serializer = SetUserPasswordInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        password = serializer.validated_data["password"]
        try:
            validate_password(password, user)
        except DjangoValidationError as exc:
            return Response({"password": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(password)
        user.save(update_fields=["password"])

        emit_audit_event(
            request,
            event_type="user.password_set",
            entity_type="user",
            entity_id=str(user.id),
            action="password_set",
            payload={},
        )
        return Response({"status": "ok"})


class DisableUserView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin, HasCapability]
    required_capability = USERS_DISABLE

    @extend_schema(
        operation_id="superAdminUsersDisable",
        request=DisableUserInputSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, user_id: int):
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        if user.id == request.user.id:
            return Response(
                {"code": "forbidden", "message": "Cannot disable your own account."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if _is_super_admin_user(user):
            return _ceo_forbidden_response(
                "Суперадмина (CEO) нельзя отключить: у него защищённый кабинет."
            )

        serializer = DisableUserInputSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        reason = (serializer.validated_data.get("reason") or "").strip()

        if user.is_active:
            user.is_active = False
            user.save(update_fields=["is_active"])

        emit_audit_event(
            request,
            event_type="user.disabled",
            entity_type="user",
            entity_id=str(user.id),
            action="disable",
            payload={"reason": reason},
        )
        return Response({"status": "disabled"})


class EnableUserView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin, HasCapability]
    required_capability = USERS_ENABLE

    @extend_schema(
        operation_id="superAdminUsersEnable",
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, user_id: int):
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])

        emit_audit_event(
            request,
            event_type="user.enabled",
            entity_type="user",
            entity_id=str(user.id),
            action="enable",
        )
        return Response({"status": "active"})


class ForceLogoutUserView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin, HasCapability]
    required_capability = USERS_FORCE_LOGOUT

    @extend_schema(
        operation_id="superAdminUsersForceLogout",
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, user_id: int):
        from rest_framework.authtoken.models import Token

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        if _is_super_admin_user(user) and user.id != request.user.id:
            return _ceo_forbidden_response(
                "Сессии суперадмина (CEO) может завершать только он сам."
            )

        revoked = Token.objects.filter(user=user).delete()[0] or 0

        emit_audit_event(
            request,
            event_type="user.force_logout",
            entity_type="user",
            entity_id=str(user.id),
            action="force_logout",
            payload={"revoked_sessions": revoked},
        )
        return Response({"revoked_sessions": revoked})


class UpdateUserRolesView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin, HasCapability]
    required_capability = ROLES_MANAGE

    @extend_schema(
        operation_id="superAdminUsersUpdateRoles",
        request=UpdateRolesInputSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def put(self, request, user_id: int):
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = UpdateRolesInputSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        roles: list[str] = payload["roles"]
        scope: str = payload.get("scope") or "global"
        reason: str = (payload.get("reason") or "").strip()

        if user.id == request.user.id and "super_admin" in _role_codes_for(user) and "super_admin" not in roles:
            return Response(
                {
                    "code": "forbidden",
                    "message": "Cannot revoke your own super_admin role.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if (
            user.id != request.user.id
            and _is_super_admin_user(user)
            and "super_admin" not in roles
        ):
            return _ceo_forbidden_response(
                "Суперадмина (CEO) нельзя понизить: его роль защищена."
            )

        organization_id = _resolve_scope_organization_id(scope)

        unknown = [code for code in roles if not Role.objects.filter(code=code).exists()]
        if unknown:
            return Response(
                {
                    "code": "validation_error",
                    "message": "Unknown role code(s).",
                    "details": {"unknown_roles": unknown},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            current_qs = UserRole.objects.filter(user=user)
            if organization_id is None:
                current_qs = current_qs.filter(organization__isnull=True)
            else:
                current_qs = current_qs.filter(organization_id=organization_id)
            current_qs.delete()

            for code in roles:
                role = Role.objects.get(code=code)
                UserRole.objects.create(
                    user=user,
                    role=role,
                    organization_id=organization_id,
                )

        emit_audit_event(
            request,
            event_type="user.roles.updated",
            entity_type="user",
            entity_id=str(user.id),
            action="update_roles",
            payload={"roles": roles, "scope": scope, "reason": reason},
        )

        user.refresh_from_db()
        return Response(PlatformUserDetailSerializer(user).data)


class UpdateUserCapabilitiesView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin, HasCapability]
    required_capability = CAPABILITIES_MANAGE

    @extend_schema(
        operation_id="superAdminUsersUpdateCapabilities",
        request=UpdateCapabilitiesInputSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def put(self, request, user_id: int):
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = UpdateCapabilitiesInputSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        add_list: list[str] = payload.get("capabilities_add", []) or []
        remove_list: list[str] = payload.get("capabilities_remove", []) or []
        scope: str = payload.get("scope") or "global"
        reason: str = (payload.get("reason") or "").strip()

        unknown = [code for code in add_list if not is_known_capability(code)]
        if unknown:
            return Response(
                {
                    "code": "validation_error",
                    "message": "Unknown capability code(s).",
                    "details": {"unknown_capabilities": unknown},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            for code in remove_list:
                UserCapability.objects.filter(
                    user=user, capability=code, scope=scope
                ).delete()
            for code in add_list:
                UserCapability.objects.get_or_create(
                    user=user,
                    capability=code,
                    scope=scope,
                    defaults={
                        "granted_by": request.user
                        if request.user.is_authenticated
                        else None,
                        "reason": reason,
                    },
                )

        emit_audit_event(
            request,
            event_type="user.capabilities.updated",
            entity_type="user",
            entity_id=str(user.id),
            action="update_capabilities",
            payload={
                "added": add_list,
                "removed": remove_list,
                "scope": scope,
                "reason": reason,
            },
        )

        user.refresh_from_db()
        return Response(PlatformUserDetailSerializer(user).data)


class CapabilityCatalogView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @extend_schema(
        operation_id="superAdminCapabilityCatalog",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        return Response(
            {
                "capabilities": list(ALL_CAPABILITIES),
                "roles": [
                    {
                        "code": "super_admin",
                        "capabilities": sorted(capabilities_for_roles({"super_admin"})),
                    },
                    {
                        "code": "company_admin",
                        "capabilities": sorted(capabilities_for_roles({"company_admin"})),
                    },
                    {
                        "code": "manager",
                        "capabilities": sorted(capabilities_for_roles({"manager"})),
                    },
                    {
                        "code": "employee",
                        "capabilities": sorted(capabilities_for_roles({"employee"})),
                    },
                    {
                        "code": "auditor",
                        "capabilities": sorted(capabilities_for_roles({"auditor"})),
                    },
                ],
            }
        )


class MyCapabilitiesView(APIView):
    """Returns the effective capability set for the authenticated user.

    Useful for frontend to drive capability-aware UI state
    without exposing the raw permission matrix.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="meCapabilities",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        caps = sorted(effective_capabilities(request.user))
        return Response({"capabilities": caps})
