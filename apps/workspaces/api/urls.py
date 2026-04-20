from django.urls import path

from .views import (
    BuildingDepartmentsView,
    BuildingDetailView,
    BuildingsListView,
    EmployeeMeProfileView,
    EmployeeProfileByIdView,
    EmployeeProfileGlobalAliasView,
    EmployeeProfileView,
    EmployeeWorkspaceCabinetView,
    EmployeeWorkspaceContextView,
    FloorWorkspaceView,
    WorkspaceContextAliasView,
    WorkspaceContextGlobalAliasView,
    WorkspaceQuickTasksView,
)

urlpatterns = [
    path("buildings", BuildingsListView.as_view(), name="buildings-list"),
    path("buildings/<str:building_id>", BuildingDetailView.as_view(), name="buildings-detail"),
    path(
        "buildings/<str:building_id>/departments",
        BuildingDepartmentsView.as_view(),
        name="buildings-departments",
    ),
    path(
        "buildings/<str:building_id>/floors/<str:floor_id>/workspace",
        FloorWorkspaceView.as_view(),
        name="workspace-floor",
    ),
    path(
        "buildings/<str:building_id>/floors/<str:floor_id>/workspace/employee/<str:employee_id>",
        EmployeeWorkspaceContextView.as_view(),
        name="workspace-employee-context",
    ),
    path(
        "buildings/<str:building_id>/floors/<str:floor_id>/employees/<str:employee_id>/profile",
        EmployeeProfileView.as_view(),
        name="employee-profile",
    ),
    path(
        "buildings/<str:building_id>/floors/<str:floor_id>/workspace-context",
        WorkspaceContextAliasView.as_view(),
        name="workspace-context-alias",
    ),
    path(
        "workspace/context",
        WorkspaceContextGlobalAliasView.as_view(),
        name="workspace-context-global-alias",
    ),
    path(
        "employees/<str:employee_id>/profile",
        EmployeeProfileGlobalAliasView.as_view(),
        name="employee-profile-global-alias",
    ),
    path("workspace", EmployeeWorkspaceCabinetView.as_view(), name="workspace"),
    path("employees/me", EmployeeMeProfileView.as_view(), name="employees-me"),
    path("employees/<str:employee_id>", EmployeeProfileByIdView.as_view(), name="employees-by-id"),
    path("workspace/quick-tasks", WorkspaceQuickTasksView.as_view(), name="workspace-quick-tasks"),
]
