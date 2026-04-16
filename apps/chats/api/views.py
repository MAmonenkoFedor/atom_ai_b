from django.db.models import Q
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.chats.models import Chat, ChatMember, Message

from .serializers import (
    ChatCreateSerializer,
    ChatSerializer,
    MessageCreateSerializer,
    MessageSerializer,
)


class ChatListCreateView(generics.ListCreateAPIView):
    queryset = Chat.objects.select_related("project", "created_by")
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ChatCreateSerializer
        return ChatSerializer

    def get_queryset(self):
        qs = self.queryset.order_by("-id")
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
        return Response(ChatSerializer(chat).data, status=status.HTTP_201_CREATED)


class ChatDetailView(generics.RetrieveAPIView):
    queryset = Chat.objects.select_related("project", "created_by")
    serializer_class = ChatSerializer
    permission_classes = [IsAuthenticated]


class ChatMessagesView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return MessageCreateSerializer
        return MessageSerializer

    def get_queryset(self):
        return Message.objects.select_related("chat", "user").filter(chat_id=self.kwargs["pk"])

    def create(self, request, *args, **kwargs):
        chat = generics.get_object_or_404(Chat, id=self.kwargs["pk"])
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = serializer.save(chat=chat, user=request.user)
        return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED)
