from django.db.models import Q
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import Project, ProjectMember

from .serializers import (
    ProjectCreateSerializer,
    ProjectMemberCreateSerializer,
    ProjectMemberSerializer,
    ProjectMemberUpdateSerializer,
    ProjectSerializer,
    ProjectUpdateSerializer,
)


class ProjectListView(generics.ListCreateAPIView):
    queryset = Project.objects.select_related("organization", "created_by")
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProjectCreateSerializer
        return ProjectSerializer

    def get_queryset(self):
        qs = self.queryset.order_by("id")
        q = self.request.query_params.get("q")
        status_param = self.request.query_params.get("status")
        department_id = self.request.query_params.get("department_id")
        owner_id = self.request.query_params.get("owner_id")
        sort = self.request.query_params.get("sort")

        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        if status_param:
            qs = qs.filter(status=status_param)
        if owner_id:
            qs = qs.filter(created_by_id=owner_id)
        if department_id:
            try:
                dep_id = int(department_id)
            except ValueError as exc:
                raise ValidationError({"detail": "Invalid department_id."}) from exc
            qs = qs.filter(created_by__org_unit_memberships__org_unit_id=dep_id).distinct()

        sort_map = {
            "name": "name",
            "-name": "-name",
            "created_at": "created_at",
            "-created_at": "-created_at",
            "id": "id",
            "-id": "-id",
        }
        if sort in sort_map:
            qs = qs.order_by(sort_map[sort])

        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = serializer.save(created_by=request.user)
        ProjectMember.objects.get_or_create(
            project=project,
            user=request.user,
            defaults={"role": ProjectMember.ROLE_OWNER, "is_active": True},
        )
        return Response(ProjectSerializer(project).data, status=status.HTTP_201_CREATED)


class ProjectDetailView(generics.RetrieveAPIView):
    queryset = Project.objects.select_related("organization", "created_by")
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return ProjectUpdateSerializer
        return ProjectSerializer

    def patch(self, request, *args, **kwargs):
        project = self.get_object()
        serializer = self.get_serializer(project, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class ProjectArchiveView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="projectArchive",
        request=None,
        responses={200: ProjectSerializer},
    )
    def post(self, request, pk: int):
        project = generics.get_object_or_404(Project, pk=pk)
        project.status = Project.STATUS_ARCHIVED
        project.save(update_fields=["status", "updated_at"])
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class ProjectRestoreView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="projectRestore",
        request=None,
        responses={200: ProjectSerializer},
    )
    def post(self, request, pk: int):
        project = generics.get_object_or_404(Project, pk=pk)
        if project.status == Project.STATUS_ARCHIVED:
            project.status = Project.STATUS_ACTIVE
            project.save(update_fields=["status", "updated_at"])
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class ProjectMembersView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProjectMemberCreateSerializer
        return ProjectMemberSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ProjectMember.objects.none()
        return ProjectMember.objects.select_related("user", "project").filter(
            project_id=self.kwargs["pk"]
        )

    def create(self, request, *args, **kwargs):
        project = generics.get_object_or_404(Project, pk=self.kwargs["pk"])
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member, _ = ProjectMember.objects.update_or_create(
            project=project,
            user=serializer.validated_data["user"],
            defaults={
                "role": serializer.validated_data.get("role", ProjectMember.ROLE_EDITOR),
                "is_active": serializer.validated_data.get("is_active", True),
            },
        )
        return Response(ProjectMemberSerializer(member).data, status=status.HTTP_201_CREATED)


class ProjectMemberDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="projectMemberUpdate",
        request=ProjectMemberUpdateSerializer,
        responses={200: ProjectMemberSerializer},
    )
    def patch(self, request, pk: int, member_id: int):
        member = generics.get_object_or_404(
            ProjectMember.objects.select_related("user", "project"),
            pk=member_id,
            project_id=pk,
        )
        serializer = ProjectMemberUpdateSerializer(member, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(ProjectMemberSerializer(member).data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="projectMemberDelete",
        request=None,
        responses={204: OpenApiResponse(description="Project member deleted")},
    )
    def delete(self, request, pk: int, member_id: int):
        member = generics.get_object_or_404(
            ProjectMember,
            pk=member_id,
            project_id=pk,
        )
        member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
