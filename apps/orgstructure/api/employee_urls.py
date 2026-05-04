from django.urls import path

from .employee_workspace_views import (
    EmployeeDepartmentsView,
    EmployeeDetailView,
    EmployeeListView,
    EmployeePermissionRevokeView,
    EmployeePermissionsView,
    EmployeeProjectsView,
    EmployeeRolesView,
    EmployeeWorkspaceView,
)

urlpatterns = [
    path("employees", EmployeeListView.as_view(), name="employees-list-v1"),
    path("employees/<int:user_id>", EmployeeDetailView.as_view(), name="employees-detail-v1"),
    path("employees/<int:user_id>/departments", EmployeeDepartmentsView.as_view(), name="employees-departments-v1"),
    path("employees/<int:user_id>/roles", EmployeeRolesView.as_view(), name="employees-roles-v1"),
    path("employees/<int:user_id>/permissions", EmployeePermissionsView.as_view(), name="employees-permissions-v1"),
    path(
        "employees/<int:user_id>/permissions/<int:grant_id>/revoke",
        EmployeePermissionRevokeView.as_view(),
        name="employees-permissions-revoke-v1",
    ),
    path("employees/<int:user_id>/projects", EmployeeProjectsView.as_view(), name="employees-projects-v1"),
    path("employees/<int:user_id>/workspace", EmployeeWorkspaceView.as_view(), name="employees-workspace-v1"),
]
