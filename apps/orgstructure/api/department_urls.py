from django.urls import path

from .department_workspace_views import (
    DepartmentDetailView,
    DepartmentDocumentLinkView,
    DepartmentDocumentUploadView,
    DepartmentDocumentsListView,
    DepartmentEmployeeDetailView,
    DepartmentEmployeesListView,
    DepartmentListView,
    DepartmentProjectsListView,
    DepartmentWorkspaceView,
)

urlpatterns = [
    path("departments", DepartmentListView.as_view(), name="departments-list"),
    path("departments/<int:pk>", DepartmentDetailView.as_view(), name="departments-detail"),
    path("departments/<int:pk>/workspace", DepartmentWorkspaceView.as_view(), name="departments-workspace"),
    path(
        "departments/<int:pk>/employees/<int:employee_id>",
        DepartmentEmployeeDetailView.as_view(),
        name="departments-employees-detail",
    ),
    path("departments/<int:pk>/employees", DepartmentEmployeesListView.as_view(), name="departments-employees"),
    path("departments/<int:pk>/projects", DepartmentProjectsListView.as_view(), name="departments-projects"),
    path("departments/<int:pk>/documents", DepartmentDocumentsListView.as_view(), name="departments-documents-list"),
    path(
        "departments/<int:pk>/documents/upload",
        DepartmentDocumentUploadView.as_view(),
        name="departments-documents-upload",
    ),
    path(
        "departments/<int:pk>/documents/link",
        DepartmentDocumentLinkView.as_view(),
        name="departments-documents-link",
    ),
]
