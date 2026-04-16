from django.urls import path

from .views import ChatDetailView, ChatListCreateView, ChatMessagesView

urlpatterns = [
    path("chats", ChatListCreateView.as_view(), name="chats-list-create"),
    path("chats/<int:pk>", ChatDetailView.as_view(), name="chats-detail"),
    path("chats/<int:pk>/messages", ChatMessagesView.as_view(), name="chats-messages"),
]
