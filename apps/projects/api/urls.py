from django.urls import path

from .views import (
    ProjectArchiveView,
    ProjectDetailView,
    ProjectListView,
    ProjectMemberDetailView,
    ProjectMembersView,
    ProjectRestoreView,
)

urlpatterns = [
    path("projects", ProjectListView.as_view(), name="projects-list"),
    path("projects/<int:pk>", ProjectDetailView.as_view(), name="projects-detail"),
    path("projects/<int:pk>/archive", ProjectArchiveView.as_view(), name="projects-archive"),
    path("projects/<int:pk>/restore", ProjectRestoreView.as_view(), name="projects-restore"),
    path("projects/<int:pk>/members", ProjectMembersView.as_view(), name="projects-members"),
    path(
        "projects/<int:pk>/members/<int:member_id>",
        ProjectMemberDetailView.as_view(),
        name="projects-member-detail",
    ),
]
