from django.urls import path

from .parallel_contract_views import (
    TaskActivityView,
    TaskDetailView,
    TasksBoardView,
    TasksBulkAssignView,
    TasksBulkStatusView,
    TasksStatsView,
    TasksView,
)

urlpatterns = [
    path("tasks", TasksView.as_view()),
    path("tasks/board", TasksBoardView.as_view()),
    path("tasks/stats", TasksStatsView.as_view()),
    path("tasks/bulk/status", TasksBulkStatusView.as_view()),
    path("tasks/bulk/assign", TasksBulkAssignView.as_view()),
    path("tasks/<int:task_id>/activity", TaskActivityView.as_view()),
    path("tasks/<int:task_id>", TaskDetailView.as_view()),
]
