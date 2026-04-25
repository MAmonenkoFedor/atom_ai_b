from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.service import emit_audit_event

from .serializers import (
    AuthLoginSerializer,
    ChangeOwnPasswordSerializer,
    EmployeeSerializer,
    InviteActivateSerializer,
    InviteActivateResponseSerializer,
    MeSerializer,
    SessionResponseSerializer,
    SessionUserSerializer,
)

User = get_user_model()


@method_decorator(ensure_csrf_cookie, name="dispatch")
class AuthCsrfCookieView(APIView):
    """Prime `csrftoken` cookie for SPA login (cross-origin POST /auth/login)."""

    permission_classes = [AllowAny]

    def get(self, request):
        # Echo token for SPAs where API host differs from the page host and `document.cookie` cannot read `csrftoken`.
        return Response({"detail": "ok", "csrfToken": get_token(request)})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = MeSerializer(request.user)
        return Response(serializer.data)


class MePasswordChangeView(APIView):
    """Смена пароля текущим пользователем (настройки профиля)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="mePasswordChange",
        request=ChangeOwnPasswordSerializer,
        responses={200: OpenApiResponse(description="Пароль обновлён")},
    )
    def post(self, request):
        serializer = ChangeOwnPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        current = serializer.validated_data["current_password"]
        new_password = serializer.validated_data["new_password"]

        if not request.user.check_password(current):
            return Response(
                {"detail": "Неверный текущий пароль."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_password(new_password, request.user)
        except DjangoValidationError as exc:
            return Response(
                {"new_password": list(exc.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(new_password)
        request.user.save(update_fields=["password"])
        update_session_auth_hash(request, request.user)

        emit_audit_event(
            request,
            event_type="user.password_changed",
            entity_type="user",
            action="password_change",
            entity_id=str(request.user.id),
            payload={},
        )

        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class AuthLoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="authLogin",
        request=AuthLoginSerializer,
        responses={200: SessionResponseSerializer},
    )
    def post(self, request):
        serializer = AuthLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data.get("username", "").strip()
        email = serializer.validated_data.get("email", "").strip().lower()
        password = serializer.validated_data["password"]

        if not username and email:
            user_by_email = User.objects.filter(email__iexact=email).first()
            username = user_by_email.username if user_by_email else ""

        user = authenticate(request, username=username, password=password)
        if user is None:
            emit_audit_event(
                request,
                event_type="auth.login.failed",
                entity_type="user",
                action="login_failed",
                entity_id="",
                payload={"username": username or email or ""},
            )
            raise AuthenticationFailed(detail="Invalid credentials.")

        login(request, user)
        if not request.session.session_key:
            request.session.create()

        emit_audit_event(
            request,
            event_type="auth.login",
            entity_type="user",
            action="login",
            entity_id=str(user.id),
            payload={"username": user.username},
        )

        payload = {
            "session": {
                "token": request.session.session_key,
                "user": SessionUserSerializer(user).data,
            }
        }
        return Response(payload, status=status.HTTP_200_OK)


class AuthLogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="authLogout",
        request=None,
        responses={204: OpenApiResponse(description="Logged out")},
    )
    def post(self, request):
        user_id = str(getattr(request.user, "id", "") or "")
        username = getattr(request.user, "username", "") or ""
        emit_audit_event(
            request,
            event_type="auth.logout",
            entity_type="user",
            action="logout",
            entity_id=user_id,
            payload={"username": username},
        )
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AuthSessionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="authSession",
        responses={200: SessionResponseSerializer},
    )
    def get(self, request):
        if not request.session.session_key:
            request.session.create()
        payload = {
            "session": {
                "token": request.session.session_key,
                "user": SessionUserSerializer(request.user).data,
            }
        }
        return Response(payload, status=status.HTTP_200_OK)


class InviteActivateView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="authInviteActivate",
        request=InviteActivateSerializer,
        responses={200: InviteActivateResponseSerializer},
    )
    def post(self, request):
        serializer = InviteActivateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data["resolved_token"]
        emit_audit_event(
            request,
            event_type="auth.invite.activated",
            entity_type="invite",
            action="invite_activated",
            entity_id=str(token)[:128],
            payload={"token_preview": str(token)[:12]},
        )
        return Response(
            {
                "detail": "Invite token accepted. Activation endpoint is available.",
                "invite_token": token,
            },
            status=status.HTTP_200_OK,
        )


class EmployeeListView(generics.ListAPIView):
    queryset = User.objects.all()
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = User.objects.all().order_by("id")
        q = self.request.query_params.get("q")
        status = self.request.query_params.get("status")
        sort = self.request.query_params.get("sort")

        if q:
            qs = qs.filter(
                Q(username__icontains=q)
                | Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
            )

        if status == "active":
            qs = qs.filter(is_active=True)
        elif status == "inactive":
            qs = qs.filter(is_active=False)

        sort_map = {
            "username": "username",
            "-username": "-username",
            "created_at": "date_joined",
            "-created_at": "-date_joined",
            "id": "id",
            "-id": "-id",
        }
        if sort in sort_map:
            qs = qs.order_by(sort_map[sort])

        return qs


class EmployeeDetailView(generics.RetrieveAPIView):
    queryset = User.objects.all()
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]
