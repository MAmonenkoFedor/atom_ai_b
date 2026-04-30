from django.urls import path

from apps.orgstructure.api.company_admin_departments import (
    CompanyAdminDepartmentDetailView,
    CompanyAdminDepartmentLeadView,
    CompanyAdminDepartmentsView,
)

from .parallel_contract_views import (
    CompanyAdminInviteRevokeView,
    CompanyAdminInvitesView,
    CompanyAdminOverviewView,
    CompanyAdminUserRoleUpdateView,
    CompanyAdminUsersView,
)

urlpatterns = [
    path("company/admin/overview", CompanyAdminOverviewView.as_view()),
    path("company/admin/departments", CompanyAdminDepartmentsView.as_view()),
    path(
        "company/admin/departments/<int:department_id>",
        CompanyAdminDepartmentDetailView.as_view(),
    ),
    path(
        "company/admin/departments/<int:department_id>/lead",
        CompanyAdminDepartmentLeadView.as_view(),
    ),
    path("company/admin/users", CompanyAdminUsersView.as_view()),
    path("company/admin/invites", CompanyAdminInvitesView.as_view()),
    path("company/admin/users/<int:user_id>/role", CompanyAdminUserRoleUpdateView.as_view()),
    path("company/admin/invites/<int:invite_id>/revoke", CompanyAdminInviteRevokeView.as_view()),
]
