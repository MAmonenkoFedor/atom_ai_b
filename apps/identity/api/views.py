from django.contrib.auth import authenticate, get_user_model, login, logout
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    AuthLoginSerializer,
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
        return Response({"detail": "ok"})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = MeSerializer(request.user)
        return Response(serializer.data)


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
            raise AuthenticationFailed(detail="Invalid credentials.")

        login(request, user)
        if not request.session.session_key:
            request.session.create()

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
        # Placeholder behavior until invite domain is implemented.
        return Response(
            {
                "detail": "Invite token accepted. Activation endpoint is available.",
                "invite_token": serializer.validated_data["resolved_token"],
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
