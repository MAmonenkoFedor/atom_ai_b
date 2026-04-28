from django.urls import path

from .views import (
    ProjectArchiveView,
    ProjectDetailView,
    ProjectDocumentLinkView,
    ProjectDocumentUploadView,
    ProjectDocumentsListView,
    ProjectLeadView,
    ProjectListView,
    ProjectMemberDetailView,
    ProjectMemberCandidatesView,
    ProjectMembersView,
    ProjectResourceRequestCompanyListView,
    ProjectResourceRequestCreateView,
    ProjectResourceRequestResolveView,
    ProjectRestoreView,
)

urlpatterns = [
    path("projects/resource-requests", ProjectResourceRequestCompanyListView.as_view(), name="projects-resource-requests-list"),
    path(
        "projects/resource-requests/<int:request_id>/resolve",
        ProjectResourceRequestResolveView.as_view(),
        name="projects-resource-requests-resolve",
    ),
    path("projects", ProjectListView.as_view(), name="projects-list"),
    path("projects/<int:pk>/lead", ProjectLeadView.as_view(), name="projects-lead"),
    path("projects/<int:pk>", ProjectDetailView.as_view(), name="projects-detail"),
    path("projects/<int:pk>/archive", ProjectArchiveView.as_view(), name="projects-archive"),
    path("projects/<int:pk>/restore", ProjectRestoreView.as_view(), name="projects-restore"),
    path("projects/<int:pk>/members", ProjectMembersView.as_view(), name="projects-members"),
    path(
        "projects/<int:pk>/member-candidates",
        ProjectMemberCandidatesView.as_view(),
        name="projects-member-candidates",
    ),
    path(
        "projects/<int:pk>/members/<int:member_id>",
        ProjectMemberDetailView.as_view(),
        name="projects-member-detail",
    ),
    path("projects/<int:pk>/documents", ProjectDocumentsListView.as_view(), name="projects-documents-list"),
    path(
        "projects/<int:pk>/documents/upload",
        ProjectDocumentUploadView.as_view(),
        name="projects-documents-upload",
    ),
    path(
        "projects/<int:pk>/documents/link",
        ProjectDocumentLinkView.as_view(),
        name="projects-documents-link",
    ),
    path(
        "projects/<int:pk>/resource-requests",
        ProjectResourceRequestCreateView.as_view(),
        name="projects-resource-requests-create",
    ),
]
