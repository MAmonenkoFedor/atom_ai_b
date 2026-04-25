from django.urls import path

from .views import AiUsageStatsView, AuditEventListView, AuditEventStatsView, AuditEventsExportView

urlpatterns = [
    path("audit/events", AuditEventListView.as_view(), name="audit-events-list"),
    path(
        "audit/events/export",
        AuditEventsExportView.as_view(),
        name="audit-events-export",
    ),
    path("audit/stats", AuditEventStatsView.as_view(), name="audit-events-stats"),
    path("audit/ai-usage-stats", AiUsageStatsView.as_view(), name="audit-ai-usage-stats"),
]
