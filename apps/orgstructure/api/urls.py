from django.urls import path

from .employee_career_views import (
    EmployeeCareerHistoryView,
    EmployeeDepartmentAssignmentDetailView,
    EmployeeDepartmentAssignmentsView,
    EmployeeJobTitleView,
    EmployeeLineManagerView,
    EmployeeProjectAssignmentDetailView,
    EmployeeProjectAssignmentsView,
)
from .views import (
    OrgUnitChildrenView,
    OrgUnitDetailView,
    OrgUnitListView,
    OrgUnitMembersView,
)

urlpatterns = [
    path("units", OrgUnitListView.as_view(), name="org-units-list"),
    path("units/<int:pk>", OrgUnitDetailView.as_view(), name="org-units-detail"),
    path("units/<int:pk>/children", OrgUnitChildrenView.as_view(), name="org-units-children"),
    path("units/<int:pk>/members", OrgUnitMembersView.as_view(), name="org-units-members"),
    path(
        "employees/<int:user_id>/career",
        EmployeeCareerHistoryView.as_view(),
        name="employee-career-history",
    ),
    path(
        "employees/<int:user_id>/profile",
        EmployeeJobTitleView.as_view(),
        name="employee-career-profile",
    ),
    path(
        "employees/<int:user_id>/assignments/org-unit",
        EmployeeDepartmentAssignmentsView.as_view(),
        name="employee-career-org-unit",
    ),
    path(
        "employees/<int:user_id>/assignments/org-unit/<int:org_unit_id>",
        EmployeeDepartmentAssignmentDetailView.as_view(),
        name="employee-career-org-unit-detail",
    ),
    path(
        "employees/<int:user_id>/assignments/project",
        EmployeeProjectAssignmentsView.as_view(),
        name="employee-career-project",
    ),
    path(
        "employees/<int:user_id>/assignments/project/<int:project_id>",
        EmployeeProjectAssignmentDetailView.as_view(),
        name="employee-career-project-detail",
    ),
    path(
        "employees/<int:user_id>/assignments/manager",
        EmployeeLineManagerView.as_view(),
        name="employee-career-manager",
    ),
]
