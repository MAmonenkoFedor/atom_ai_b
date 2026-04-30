from django.urls import path

from apps.projects.api.views import (
    ProjectArchiveView,
    ProjectDetailView,
    ProjectListView,
    ProjectMemberDetailView,
    ProjectMembersView,
    ProjectResourceRequestCompanyListView,
    ProjectResourceRequestCreateView,
    ProjectResourceRequestResolveView,
    ProjectRestoreView,
)

urlpatterns = [
    path("projects/resource-requests", ProjectResourceRequestCompanyListView.as_view()),
    path(
        "projects/resource-requests/<int:request_id>/resolve",
        ProjectResourceRequestResolveView.as_view(),
    ),
    path("projects", ProjectListView.as_view()),
    path("projects/<int:pk>", ProjectDetailView.as_view()),
    path("projects/<int:pk>/archive", ProjectArchiveView.as_view()),
    path("projects/<int:pk>/restore", ProjectRestoreView.as_view()),
    path("projects/<int:pk>/members", ProjectMembersView.as_view()),
    path("projects/<int:pk>/members/<int:member_id>", ProjectMemberDetailView.as_view()),
    path("projects/<int:pk>/resource-requests", ProjectResourceRequestCreateView.as_view()),
]
