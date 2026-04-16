from django.urls import path

from .views import AiRunCreateView, AiRunDetailView, AiRunExecuteView, AiRunLogsView

urlpatterns = [
    path("ai/runs", AiRunCreateView.as_view(), name="ai-runs-create"),
    path("ai/runs/<int:pk>", AiRunDetailView.as_view(), name="ai-runs-detail"),
    path("ai/runs/<int:pk>/execute", AiRunExecuteView.as_view(), name="ai-runs-execute"),
    path("ai/runs/<int:pk>/logs", AiRunLogsView.as_view(), name="ai-runs-logs"),
]
