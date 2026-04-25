from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.service import emit_audit_event
from apps.chats.chat_attachments import (
    create_chat_attachment_upload,
    delete_chat_attachment,
    list_chat_attachments,
)
from apps.chats.models import Chat, ChatMember, Message
from django.contrib.auth import get_user_model
from apps.projects.project_permissions import (
    PROJECT_SCOPE,
    can_moderate_project_chat,
    can_view_project,
)

from .serializers import (
    ChatCreateSerializer,
    ChatMemberCreateSerializer,
    ChatMemberSerializer,
    ChatMemberUpdateSerializer,
    ChatSerializer,
    ChatUpdateSerializer,
    MessageCreateSerializer,
    MessageSerializer,
)

User = get_user_model()


def _project_grant_chat_ids(user) -> set[int]:
    """Chat ids whose project the user has any active project-scoped grant for.

    This is the bulk-friendly mirror of the action-level check that lives in
    ``_require_chat_owner``: any user that can moderate or otherwise act on
    a project's chat must also be able to *see* it in the queryset, otherwise
    the list/detail view becomes inconsistent with the write check.
    """

    if not user or not getattr(user, "is_authenticated", False):
        return set()

    try:
        from apps.access.models import PermissionGrant
    except Exception:
        return set()

    now = timezone.now()
    project_ids: set[int] = set()
    rows = (
        PermissionGrant.objects.filter(
            employee=user,
            scope_type=PROJECT_SCOPE,
            status=PermissionGrant.STATUS_ACTIVE,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .values_list("scope_id", flat=True)
    )
    for raw in rows:
        try:
            project_ids.add(int(raw))
        except (TypeError, ValueError):
            continue
    if not project_ids:
        return set()
    return set(
        Chat.objects.filter(project_id__in=project_ids).values_list("id", flat=True)
    )


def _user_chat_visibility_q(user) -> Q:
    """Single Q expression that decides whether a chat is visible to ``user``."""

    base = Q(created_by_id=user.id) | Q(members__user_id=user.id)
    grant_chat_ids = _project_grant_chat_ids(user)
    if grant_chat_ids:
        base = base | Q(id__in=grant_chat_ids)
    return base


def _get_chat_or_deny(user, chat_id: int) -> Chat:
    chat = generics.get_object_or_404(Chat.objects.select_related("project"), id=chat_id)
    if chat.created_by_id == user.id:
        return chat
    if chat.members.filter(user_id=user.id).exists():
        return chat
    if chat.project_id and can_view_project(user, chat.project):
        return chat
    raise PermissionDenied("You do not have access to this chat.")


def _require_chat_owner(user, chat: Chat) -> None:
    if chat.created_by_id == user.id:
        return
    if chat.members.filter(user_id=user.id, role=ChatMember.ROLE_OWNER).exists():
        return
    if chat.project_id and can_moderate_project_chat(user, chat.project):
        return
    raise PermissionDenied("Only chat owner can manage members.")


class ChatListCreateView(generics.ListCreateAPIView):
    queryset = Chat.objects.select_related("project", "created_by")
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ChatCreateSerializer
        return ChatSerializer

    def get_queryset(self):
        qs = (
            self.queryset.filter(_user_chat_visibility_q(self.request.user))
            .distinct()
            .order_by("-id")
        )
        q = self.request.query_params.get("q")
        status_param = self.request.query_params.get("status")
        sort = self.request.query_params.get("sort")
        project_id = self.request.query_params.get("project_id")

        if project_id:
            qs = qs.filter(project_id=project_id)
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(project__name__icontains=q))
        if status_param:
            qs = qs.filter(status=status_param)

        sort_map = {
            "created_at": "created_at",
            "-created_at": "-created_at",
            "id": "id",
            "-id": "-id",
            "title": "title",
            "-title": "-title",
        }
        if sort in sort_map:
            qs = qs.order_by(sort_map[sort])

        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        chat = serializer.save(created_by=request.user)
        ChatMember.objects.get_or_create(
            chat=chat,
            user=request.user,
            defaults={"role": ChatMember.ROLE_OWNER},
        )
        emit_audit_event(
            request,
            event_type="chat.created",
            entity_type="chat",
            action="create",
            entity_id=str(chat.pk),
            project_id=str(chat.project_id or ""),
            chat_id=str(chat.pk),
            payload={"title": chat.title},
        )
        return Response(ChatSerializer(chat).data, status=status.HTTP_201_CREATED)


class ChatDetailView(generics.RetrieveAPIView):
    queryset = Chat.objects.select_related("project", "created_by")
    serializer_class = ChatSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            self.queryset.filter(_user_chat_visibility_q(self.request.user))
            .distinct()
            .order_by("-id")
        )

    def patch(self, request, *args, **kwargs):
        chat = _get_chat_or_deny(request.user, int(self.kwargs["pk"]))
        _require_chat_owner(request.user, chat)
        serializer = ChatUpdateSerializer(chat, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        emit_audit_event(
            request,
            event_type="chat.updated",
            entity_type="chat",
            action="update",
            entity_id=str(chat.pk),
            project_id=str(chat.project_id or ""),
            chat_id=str(chat.pk),
            payload={"fields": sorted(serializer.validated_data.keys())},
        )
        return Response(ChatSerializer(chat).data, status=status.HTTP_200_OK)


class ChatMessagesView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return MessageCreateSerializer
        return MessageSerializer

    def get_queryset(self):
        chat = _get_chat_or_deny(self.request.user, int(self.kwargs["pk"]))
        return Message.objects.select_related("chat", "user").filter(chat_id=chat.pk)

    def create(self, request, *args, **kwargs):
        chat = _get_chat_or_deny(self.request.user, int(self.kwargs["pk"]))
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = serializer.save(chat=chat, user=request.user)
        emit_audit_event(
            request,
            event_type="chat.message_created",
            entity_type="chat_message",
            action="create",
            entity_id=str(message.pk),
            project_id=str(chat.project_id or ""),
            chat_id=str(chat.pk),
            payload={"content_len": len(message.content or "")},
        )
        return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED)


class ChatMembersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        chat = _get_chat_or_deny(request.user, pk)
        members = ChatMember.objects.select_related("user", "chat").filter(chat_id=chat.pk)
        return Response({"results": ChatMemberSerializer(members, many=True).data})

    def post(self, request, pk: int):
        chat = _get_chat_or_deny(request.user, pk)
        _require_chat_owner(request.user, chat)
        serializer = ChatMemberCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.get(id=serializer.validated_data["user_id"])
        role = serializer.validated_data["role"]
        member, created = ChatMember.objects.update_or_create(
            chat=chat,
            user=user,
            defaults={"role": role},
        )
        emit_audit_event(
            request,
            event_type="chat.member_upserted",
            entity_type="chat_member",
            action="upsert",
            entity_id=f"{chat.pk}:{user.id}",
            project_id=str(chat.project_id or ""),
            chat_id=str(chat.pk),
            payload={"member_user_id": user.id, "role": role, "created": created},
        )
        return Response(
            ChatMemberSerializer(member).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ChatMemberDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk: int, user_id: int):
        chat = _get_chat_or_deny(request.user, pk)
        _require_chat_owner(request.user, chat)
        member = generics.get_object_or_404(ChatMember, chat_id=chat.pk, user_id=user_id)
        serializer = ChatMemberUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_role = serializer.validated_data["role"]

        if member.role == ChatMember.ROLE_OWNER and new_role != ChatMember.ROLE_OWNER:
            other_owners_exist = ChatMember.objects.filter(
                chat_id=chat.pk,
                role=ChatMember.ROLE_OWNER,
            ).exclude(user_id=member.user_id).exists()
            if not other_owners_exist:
                raise ValidationError(
                    {"detail": "Cannot demote the last chat owner. Promote another owner first."}
                )

        if member.user_id == chat.created_by_id and new_role != ChatMember.ROLE_OWNER:
            raise ValidationError({"detail": "Chat creator must remain owner."})

        member.role = new_role
        member.save(update_fields=["role"])
        emit_audit_event(
            request,
            event_type="chat.member_updated",
            entity_type="chat_member",
            action="update",
            entity_id=f"{chat.pk}:{user_id}",
            project_id=str(chat.project_id or ""),
            chat_id=str(chat.pk),
            payload={"member_user_id": user_id, "role": new_role},
        )
        return Response(ChatMemberSerializer(member).data, status=status.HTTP_200_OK)

    def delete(self, request, pk: int, user_id: int):
        chat = _get_chat_or_deny(request.user, pk)
        _require_chat_owner(request.user, chat)
        member = generics.get_object_or_404(ChatMember, chat_id=chat.pk, user_id=user_id)

        if member.user_id == chat.created_by_id:
            raise ValidationError({"detail": "Chat creator cannot be removed from members."})

        if member.user_id == request.user.id and member.role == ChatMember.ROLE_OWNER:
            other_owners_exist = ChatMember.objects.filter(
                chat_id=chat.pk, role=ChatMember.ROLE_OWNER
            ).exclude(user_id=request.user.id).exists()
            if not other_owners_exist:
                raise ValidationError(
                    {"detail": "Cannot remove the last chat owner. Add another owner first."}
                )
        member.delete()
        emit_audit_event(
            request,
            event_type="chat.member_removed",
            entity_type="chat_member",
            action="delete",
            entity_id=f"{chat.pk}:{user_id}",
            project_id=str(chat.project_id or ""),
            chat_id=str(chat.pk),
            payload={"member_user_id": user_id},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChatAttachmentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        chat = _get_chat_or_deny(request.user, pk)
        return Response({"results": list_chat_attachments(request, chat)})

    def post(self, request, pk: int):
        chat = _get_chat_or_deny(request.user, pk)
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": "No file uploaded."})
        data = create_chat_attachment_upload(request, chat, upload)
        emit_audit_event(
            request,
            event_type="chat.attachment_created",
            entity_type="chat_attachment",
            action="create",
            entity_id=str(data.get("id", "")),
            project_id=str(chat.project_id or ""),
            chat_id=str(chat.pk),
            payload={"title": data.get("title", ""), "size_bytes": data.get("size_bytes", 0)},
        )
        return Response(data, status=status.HTTP_201_CREATED)


class ChatAttachmentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk: int, attachment_id: int):
        chat = _get_chat_or_deny(request.user, pk)
        delete_chat_attachment(request, chat, attachment_id)
        emit_audit_event(
            request,
            event_type="chat.attachment_deleted",
            entity_type="chat_attachment",
            action="delete",
            entity_id=f"catt-{attachment_id}",
            project_id=str(chat.project_id or ""),
            chat_id=str(chat.pk),
            payload={"attachment_id": attachment_id},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
