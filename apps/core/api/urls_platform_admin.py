from django.urls import path

from .parallel_contract_views import (
    AdminActionDetailView,
    AdminActionEventsView,
    AdminActionStatsView,
    PlatformAuditEventsView,
    PlatformAuditExportView,
    PlatformAuditStatsView,
    PlatformInviteRevokeView,
    PlatformInvitesView,
    PlatformOverviewView,
    PlatformTenantsView,
    PlatformTenantStatusView,
    PlatformUsersView,
)

urlpatterns = [
    path("admin/platform/overview", PlatformOverviewView.as_view()),
    path("admin/platform/tenants", PlatformTenantsView.as_view()),
    path("admin/platform/users", PlatformUsersView.as_view()),
    path("admin/platform/invites", PlatformInvitesView.as_view()),
    path("admin/platform/tenants/<int:tenant_id>/status", PlatformTenantStatusView.as_view()),
    path("admin/platform/invites/<int:invite_id>/revoke", PlatformInviteRevokeView.as_view()),
    path("admin/platform/audit/stats", PlatformAuditStatsView.as_view()),
    path("admin/platform/audit/events", PlatformAuditEventsView.as_view()),
    path("admin/platform/audit/export", PlatformAuditExportView.as_view()),
    path("admin/actions/stats", AdminActionStatsView.as_view()),
    path("admin/actions/events", AdminActionEventsView.as_view()),
    path("admin/actions/events/<int:action_id>", AdminActionDetailView.as_view()),
]
