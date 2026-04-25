from django.urls import path

from .views import (
    ChatAttachmentDetailView,
    ChatAttachmentsView,
    ChatDetailView,
    ChatListCreateView,
    ChatMemberDetailView,
    ChatMembersView,
    ChatMessagesView,
)

urlpatterns = [
    path("chats", ChatListCreateView.as_view(), name="chats-list-create"),
    path("chats/<int:pk>", ChatDetailView.as_view(), name="chats-detail"),
    path("chats/<int:pk>/attachments", ChatAttachmentsView.as_view(), name="chats-attachments"),
    path(
        "chats/<int:pk>/attachments/<int:attachment_id>",
        ChatAttachmentDetailView.as_view(),
        name="chats-attachment-detail",
    ),
    path("chats/<int:pk>/messages", ChatMessagesView.as_view(), name="chats-messages"),
    path("chats/<int:pk>/members", ChatMembersView.as_view(), name="chats-members"),
    path("chats/<int:pk>/members/<int:user_id>", ChatMemberDetailView.as_view(), name="chats-member-detail"),
]
