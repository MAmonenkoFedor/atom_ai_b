from django.urls import path

from .views import (
    AiChatCompletionsView,
    AiModelsListView,
    AiRunCreateView,
    AiRunDetailView,
    AiRunExecuteView,
    AiRunLogsView,
)

urlpatterns = [
    path("ai/runs", AiRunCreateView.as_view(), name="ai-runs-create"),
    path("ai/runs/<int:pk>", AiRunDetailView.as_view(), name="ai-runs-detail"),
    path("ai/runs/<int:pk>/execute", AiRunExecuteView.as_view(), name="ai-runs-execute"),
    path("ai/runs/<int:pk>/logs", AiRunLogsView.as_view(), name="ai-runs-logs"),
    path("ai/chat/completions", AiChatCompletionsView.as_view(), name="ai-chat-completions"),
    path("ai/models", AiModelsListView.as_view(), name="ai-models-list"),
]
