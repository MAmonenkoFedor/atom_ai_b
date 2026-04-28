from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.service import emit_audit_event
from apps.core.api.permissions import IsCompanyAdminOrSuperAdmin, normalized_roles_for_user
from apps.organizations.models import OrganizationMember
from apps.orgstructure.models import OrgUnitMember
from apps.projects import project_documents as project_documents_service
from apps.projects.list_annotations import (
    annotate_for_project_list,
    base_project_queryset,
    projects_queryset_with_annotations,
)
from apps.projects.lead_payload import batch_project_lead_payload
from apps.projects.models import Project, ProjectMember, ProjectResourceRequest
from apps.projects.project_lead import assign_project_lead, clear_project_lead, get_project_for_lead_endpoint
from apps.projects.project_permissions import (
    require_project_action,
    require_view_project,
)
from apps.projects.task_counts import get_task_counts_by_project_id
from apps.workspaces.api.serializers import DocumentSerializer

from .serializers import (
    ProjectCreateSerializer,
    ProjectDocumentLinkCreateSerializer,
    ProjectMemberCreateSerializer,
    ProjectMemberCandidateSerializer,
    ProjectMemberSerializer,
    ProjectMemberUpdateSerializer,
    ProjectResourceRequestCreateSerializer,
    ProjectResourceRequestSerializer,
    ProjectSerializer,
    ProjectUpdateSerializer,
)

User = get_user_model()


class ProjectListView(generics.ListCreateAPIView):
    queryset = base_project_queryset()
    permission_classes = [IsAuthenticated]
    # Global DRF filter backends expect search_fields / filterset_class on this view and can 500.
    filter_backends: list = []

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProjectCreateSerializer
        return ProjectSerializer

    def get_queryset(self):
        qs = projects_queryset_with_annotations(self.request.user).order_by("id")
        q = self.request.query_params.get("q")
        status_param = self.request.query_params.get("status")
        department_id = self.request.query_params.get("department_id")
        owner_id = self.request.query_params.get("owner_id")
        sort = self.request.query_params.get("sort")
        scope = self.request.query_params.get("scope")

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

        # org_unit: проекты, привязанные к орг-юниту, в котором состоит пользователь (контекст иерархии, не «дом»).
        if scope in ("org_unit", "department_home"):
            ou_ids = list(
                OrgUnitMember.objects.filter(user=self.request.user).values_list(
                    "org_unit_id",
                    flat=True,
                )
            )
            if ou_ids:
                qs = qs.filter(primary_org_unit_id__in=ou_ids)
            else:
                qs = qs.none()
        elif scope == "member_of":
            qs = qs.filter(members__user=self.request.user).distinct()

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

        return annotate_for_project_list(qs, self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            projects = list(page)
            serializer = self.get_serializer(
                projects,
                many=True,
                context=self._context_with_lead(projects),
            )
            return self.get_paginated_response(serializer.data)
        projects = list(queryset)
        serializer = self.get_serializer(
            projects,
            many=True,
            context=self._context_with_lead(projects),
        )
        return Response(serializer.data)

    def _context_with_lead(self, projects: list):
        ctx = super().get_serializer_context()
        ctx["project_task_counts"] = get_task_counts_by_project_id()
        if projects:
            ctx["project_lead_payload"] = batch_project_lead_payload([p.pk for p in projects])
        return ctx

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["project_task_counts"] = get_task_counts_by_project_id()
        return context

    @staticmethod
    def _resolve_project_owner_user(request, organization):
        roles = normalized_roles_for_user(request.user)
        raw = request.data.get("owner_user_id")
        if raw is None:
            raw = request.data.get("ownerId")
        if raw is None:
            raw = request.data.get("owner_id")
        if raw in (None, ""):
            return request.user
        try:
            uid = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                {"owner_user_id": "Укажите числовой идентификатор пользователя (user id)."}
            ) from exc
        owner = User.objects.filter(pk=uid).first()
        if not owner:
            raise ValidationError({"owner_user_id": "Пользователь не найден."})
        if not OrganizationMember.objects.filter(
            user=owner, organization=organization, is_active=True
        ).exists():
            raise ValidationError({"owner_user_id": "Пользователь не состоит в этой организации."})
        if owner.pk == request.user.pk:
            return owner
        if "company_admin" not in roles and "super_admin" not in roles:
            raise PermissionDenied(
                "Назначать другого владельца проекта могут только администраторы компании или платформы."
            )
        return owner

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = serializer.validated_data["organization"]
        owner_user = self._resolve_project_owner_user(request, organization)
        project = serializer.save(created_by=owner_user)
        ProjectMember.objects.update_or_create(
            project=project,
            user=owner_user,
            defaults={"role": ProjectMember.ROLE_OWNER, "is_active": True},
        )
        if request.user.pk != owner_user.pk:
            ProjectMember.objects.update_or_create(
                project=project,
                user=request.user,
                defaults={"role": ProjectMember.ROLE_EDITOR, "is_active": True},
            )
        project_out = projects_queryset_with_annotations(self.request.user).get(pk=project.pk)
        emit_audit_event(
            request,
            event_type="project.created",
            entity_type="project",
            action="create",
            entity_id=str(project.pk),
            project_id=str(project.pk),
            payload={"name": project.name, "status": project.status},
        )
        out_ctx = self.get_serializer_context()
        out_ctx["project_lead_payload"] = batch_project_lead_payload([project.pk])
        return Response(
            ProjectSerializer(project_out, context=out_ctx).data,
            status=status.HTTP_201_CREATED,
        )


class ProjectLeadView(APIView):
    """Назначение/снятие руководителя проекта и пакетных project-scoped прав."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="projectLeadAssign",
        request=None,
        responses={200: ProjectSerializer},
    )
    def post(self, request, pk: int):
        project = get_project_for_lead_endpoint(request, int(pk))
        raw_uid = request.data.get("user_id")
        if raw_uid in (None, ""):
            raise ValidationError({"user_id": "Укажите пользователя."})
        try:
            user = User.objects.get(pk=int(raw_uid))
        except (User.DoesNotExist, TypeError, ValueError) as exc:
            raise ValidationError({"user_id": "Пользователь не найден."}) from exc
        assign_project_lead(
            request=request,
            project=project,
            user=user,
            grant_project_edit=bool(request.data.get("grant_project_edit", False)),
            grant_project_assign_members=bool(request.data.get("grant_project_assign_members", False)),
            grant_project_docs_view=bool(request.data.get("grant_project_docs_view", False)),
            grant_project_docs_upload=bool(request.data.get("grant_project_docs_upload", False)),
            grant_project_docs_edit=bool(request.data.get("grant_project_docs_edit", False)),
            grant_project_docs_assign_editors=bool(
                request.data.get("grant_project_docs_assign_editors", False)
            ),
            grant_project_tasks_view=bool(request.data.get("grant_project_tasks_view", False)),
            grant_project_tasks_create=bool(request.data.get("grant_project_tasks_create", False)),
            grant_project_tasks_assign=bool(request.data.get("grant_project_tasks_assign", False)),
            grant_project_tasks_change_deadline=bool(
                request.data.get("grant_project_tasks_change_deadline", False)
            ),
        )
        updated = projects_queryset_with_annotations(request.user).get(pk=project.pk)
        out_ctx = {
            "request": request,
            "project_task_counts": get_task_counts_by_project_id(),
            "project_lead_payload": batch_project_lead_payload([project.pk]),
        }
        return Response(ProjectSerializer(updated, context=out_ctx).data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="projectLeadClear",
        request=None,
        responses={200: ProjectSerializer},
    )
    def delete(self, request, pk: int):
        project = get_project_for_lead_endpoint(request, int(pk))
        clear_project_lead(request=request, project=project)
        updated = projects_queryset_with_annotations(request.user).get(pk=project.pk)
        out_ctx = {
            "request": request,
            "project_task_counts": get_task_counts_by_project_id(),
            "project_lead_payload": batch_project_lead_payload([project.pk]),
        }
        return Response(ProjectSerializer(updated, context=out_ctx).data, status=status.HTTP_200_OK)


class ProjectDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return projects_queryset_with_annotations(self.request.user)

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return ProjectUpdateSerializer
        return ProjectSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["project_task_counts"] = get_task_counts_by_project_id()
        raw_pk = self.kwargs.get("pk")
        if raw_pk is not None:
            try:
                context["project_lead_payload"] = batch_project_lead_payload([int(raw_pk)])
            except (TypeError, ValueError):
                pass
        return context

    def get_object(self):
        obj = super().get_object()
        require_view_project(self.request.user, obj)
        return obj

    def patch(self, request, *args, **kwargs):
        project = self.get_object()
        require_project_action(
            request.user,
            project,
            "project.edit",
            "You do not have permission to edit this project.",
        )
        serializer = self.get_serializer(project, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        updated = self.get_queryset().get(pk=project.pk)
        emit_audit_event(
            request,
            event_type="project.updated",
            entity_type="project",
            action="update",
            entity_id=str(project.pk),
            project_id=str(project.pk),
            payload={"fields": sorted(serializer.validated_data.keys())},
        )
        return Response(
            ProjectSerializer(updated, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )


class ProjectArchiveView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="projectArchive",
        request=None,
        responses={200: ProjectSerializer},
    )
    def post(self, request, pk: int):
        project = generics.get_object_or_404(projects_queryset_with_annotations(request.user), pk=pk)
        require_project_action(
            request.user,
            project,
            "project.edit",
            "You do not have permission to archive this project.",
        )
        project.status = Project.STATUS_ARCHIVED
        project.save(update_fields=["status", "updated_at"])
        updated = projects_queryset_with_annotations(request.user).get(pk=pk)
        emit_audit_event(
            request,
            event_type="project.archived",
            entity_type="project",
            action="archive",
            entity_id=str(pk),
            project_id=str(pk),
        )
        return Response(
            ProjectSerializer(
                updated,
                context={"request": request, "project_task_counts": get_task_counts_by_project_id()},
            ).data,
            status=status.HTTP_200_OK,
        )


class ProjectRestoreView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="projectRestore",
        request=None,
        responses={200: ProjectSerializer},
    )
    def post(self, request, pk: int):
        project = generics.get_object_or_404(projects_queryset_with_annotations(request.user), pk=pk)
        require_project_action(
            request.user,
            project,
            "project.edit",
            "You do not have permission to restore this project.",
        )
        if project.status == Project.STATUS_ARCHIVED:
            project.status = Project.STATUS_ACTIVE
            project.save(update_fields=["status", "updated_at"])
        updated = projects_queryset_with_annotations(request.user).get(pk=pk)
        emit_audit_event(
            request,
            event_type="project.restored",
            entity_type="project",
            action="restore",
            entity_id=str(pk),
            project_id=str(pk),
        )
        return Response(
            ProjectSerializer(
                updated,
                context={"request": request, "project_task_counts": get_task_counts_by_project_id()},
            ).data,
            status=status.HTTP_200_OK,
        )


class ProjectMembersView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProjectMemberCreateSerializer
        return ProjectMemberSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ProjectMember.objects.none()
        project = generics.get_object_or_404(projects_queryset_with_annotations(self.request.user), pk=self.kwargs["pk"])
        require_view_project(self.request.user, project)
        return ProjectMember.objects.select_related("user", "project").filter(
            project_id=self.kwargs["pk"],
        )

    def create(self, request, *args, **kwargs):
        project = generics.get_object_or_404(projects_queryset_with_annotations(request.user), pk=self.kwargs["pk"])
        require_project_action(
            request.user,
            project,
            "project.assign_members",
            "You do not have permission to manage project members.",
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        defaults = {
            "role": serializer.validated_data.get("role", ProjectMember.ROLE_EDITOR),
            "is_active": serializer.validated_data.get("is_active", True),
        }
        if "title_in_project" in serializer.validated_data:
            defaults["title_in_project"] = serializer.validated_data["title_in_project"] or ""
        if "engagement_weight" in serializer.validated_data:
            defaults["engagement_weight"] = serializer.validated_data["engagement_weight"]
        if "contribution_note" in serializer.validated_data:
            defaults["contribution_note"] = serializer.validated_data["contribution_note"] or ""
        member, _ = ProjectMember.objects.update_or_create(
            project=project,
            user=serializer.validated_data["user"],
            defaults=defaults,
        )
        emit_audit_event(
            request,
            event_type="project.member_upserted",
            entity_type="project_member",
            action="upsert",
            entity_id=str(member.pk),
            project_id=str(project.pk),
            payload={"employee_id": str(member.user_id), "role": member.role},
        )
        return Response(ProjectMemberSerializer(member).data, status=status.HTTP_201_CREATED)


class ProjectMemberCandidatesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="projectMemberCandidatesList",
        responses={200: ProjectMemberCandidateSerializer(many=True)},
    )
    def get(self, request, pk: int):
        project = generics.get_object_or_404(projects_queryset_with_annotations(request.user), pk=pk)
        require_project_action(
            request.user,
            project,
            "project.assign_members",
            "You do not have permission to manage project members.",
        )

        org_memberships = list(
            OrganizationMember.objects.filter(
                organization_id=project.organization_id,
                is_active=True,
                user__is_active=True,
            )
            .select_related("user")
            .order_by("user__first_name", "user__last_name", "user__username")
        )
        user_ids = [m.user_id for m in org_memberships]
        first_dept_by_user: dict[int, tuple[int, str]] = {}
        if user_ids:
            for row in (
                OrgUnitMember.objects.filter(user_id__in=user_ids, org_unit__is_active=True)
                .select_related("org_unit")
                .order_by("user_id", "id")
            ):
                if row.user_id in first_dept_by_user:
                    continue
                first_dept_by_user[row.user_id] = (row.org_unit_id, row.org_unit.name or "")

        data = []
        for membership in org_memberships:
            user = membership.user
            full_name = (user.get_full_name() or user.username or "").strip()
            dep = first_dept_by_user.get(user.id)
            data.append(
                {
                    "id": user.id,
                    "full_name": full_name,
                    "email": user.email or "",
                    "department_id": dep[0] if dep else None,
                    "department_name": dep[1] if dep else "",
                }
            )
        return Response(data, status=status.HTTP_200_OK)


class ProjectMemberDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="projectMemberUpdate",
        request=ProjectMemberUpdateSerializer,
        responses={200: ProjectMemberSerializer},
    )
    def patch(self, request, pk: int, member_id: int):
        project = generics.get_object_or_404(projects_queryset_with_annotations(request.user), pk=pk)
        member = generics.get_object_or_404(
            ProjectMember.objects.select_related("user", "project"),
            pk=member_id,
            project_id=pk,
        )
        # Invited employee accepts their own membership (is_active: true only).
        if member.user_id == request.user.id and not member.is_active:
            serializer = ProjectMemberUpdateSerializer(member, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            keys = set(serializer.validated_data.keys())
            if keys != {"is_active"} or serializer.validated_data.get("is_active") is not True:
                raise ValidationError(
                    {"detail": "Pending members may only PATCH {\"is_active\": true} to accept the invitation."}
                )
            serializer.save()
            emit_audit_event(
                request,
                event_type="project.member_self_activated",
                entity_type="project_member",
                action="update",
                entity_id=str(member.pk),
                project_id=str(pk),
                payload={"employee_id": str(member.user_id)},
            )
            member.refresh_from_db()
            return Response(ProjectMemberSerializer(member).data, status=status.HTTP_200_OK)

        serializer = ProjectMemberUpdateSerializer(member, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        require_project_action(
            request.user,
            project,
            "project.assign_members",
            "You do not have permission to update project members.",
        )
        serializer.save()
        emit_audit_event(
            request,
            event_type="project.member_updated",
            entity_type="project_member",
            action="update",
            entity_id=str(member.pk),
            project_id=str(pk),
            payload={"fields": sorted(serializer.validated_data.keys())},
        )
        member.refresh_from_db()
        return Response(ProjectMemberSerializer(member).data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="projectMemberDelete",
        request=None,
        responses={204: OpenApiResponse(description="Project member deleted")},
    )
    def delete(self, request, pk: int, member_id: int):
        project = generics.get_object_or_404(projects_queryset_with_annotations(request.user), pk=pk)
        require_project_action(
            request.user,
            project,
            "project.assign_members",
            "You do not have permission to remove project members.",
        )
        member = generics.get_object_or_404(
            ProjectMember,
            pk=member_id,
            project_id=pk,
        )
        member_user_id = member.user_id
        member.delete()
        emit_audit_event(
            request,
            event_type="project.member_deleted",
            entity_type="project_member",
            action="delete",
            entity_id=str(member_id),
            project_id=str(pk),
            payload={"employee_id": str(member_user_id)},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectDocumentsListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="projectDocumentsList", responses=DocumentSerializer(many=True))
    def get(self, request, pk: int):
        project = generics.get_object_or_404(projects_queryset_with_annotations(request.user), pk=pk)
        docs = project_documents_service.list_project_documents(request, project)
        return Response(docs)


class ProjectDocumentUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(operation_id="projectDocumentUpload", responses=DocumentSerializer)
    def post(self, request, pk: int):
        project = generics.get_object_or_404(projects_queryset_with_annotations(request.user), pk=pk)
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": "No file uploaded."})
        doc = project_documents_service.create_project_document_upload(request, project, upload)
        emit_audit_event(
            request,
            event_type="project.document_uploaded",
            entity_type="project_document",
            action="create",
            entity_id=str(doc.get("id") or ""),
            project_id=str(pk),
            payload={"title": doc.get("title"), "type": doc.get("type")},
        )
        return Response(doc, status=status.HTTP_201_CREATED)


class ProjectDocumentLinkView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="projectDocumentLinkCreate",
        request=ProjectDocumentLinkCreateSerializer,
        responses=DocumentSerializer,
    )
    def post(self, request, pk: int):
        project = generics.get_object_or_404(projects_queryset_with_annotations(request.user), pk=pk)
        serializer = ProjectDocumentLinkCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doc = project_documents_service.create_project_document_link(
            request,
            project,
            serializer.validated_data["title"],
            str(serializer.validated_data["url"]),
        )
        emit_audit_event(
            request,
            event_type="project.document_linked",
            entity_type="project_document",
            action="create",
            entity_id=str(doc.get("id") or ""),
            project_id=str(pk),
            payload={"title": doc.get("title"), "type": "link"},
        )
        return Response(doc, status=status.HTTP_201_CREATED)


def _resource_requests_base_queryset():
    return ProjectResourceRequest.objects.filter(status=ProjectResourceRequest.STATUS_OPEN).select_related(
        "project",
        "created_by",
    )


def _resource_requests_visible_to_user(user):
    qs = _resource_requests_base_queryset().order_by("-created_at", "-id")
    roles = normalized_roles_for_user(user)
    if "super_admin" in roles:
        return qs
    org_ids = list(
        OrganizationMember.objects.filter(user=user, is_active=True).values_list("organization_id", flat=True)
    )
    if not org_ids:
        return ProjectResourceRequest.objects.none()
    return qs.filter(project__organization_id__in=org_ids)


def _user_can_resolve_resource_request(user, req: ProjectResourceRequest) -> bool:
    roles = normalized_roles_for_user(user)
    if "super_admin" in roles:
        return True
    org_ids = set(
        OrganizationMember.objects.filter(user=user, is_active=True).values_list("organization_id", flat=True)
    )
    return req.project.organization_id in org_ids


class ProjectResourceRequestCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="projectResourceRequestCreate",
        request=ProjectResourceRequestCreateSerializer,
        responses={201: ProjectResourceRequestSerializer},
    )
    def post(self, request, pk: int):
        project = generics.get_object_or_404(projects_queryset_with_annotations(request.user), pk=pk)
        require_project_action(
            request.user,
            project,
            "project.assign_members",
            "You do not have permission to request project resources.",
        )
        serializer = ProjectResourceRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        req = ProjectResourceRequest.objects.create(
            project=project,
            created_by=request.user,
            message=serializer.validated_data["message"].strip(),
        )
        req = ProjectResourceRequest.objects.select_related("project", "created_by").get(pk=req.pk)
        emit_audit_event(
            request,
            event_type="project.resource_request_created",
            entity_type="project_resource_request",
            action="create",
            entity_id=str(req.pk),
            project_id=str(project.pk),
            payload={"project_name": project.name},
        )
        return Response(ProjectResourceRequestSerializer(req).data, status=status.HTTP_201_CREATED)


class ProjectResourceRequestCompanyListView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    @extend_schema(
        operation_id="projectResourceRequestCompanyList",
        responses={200: ProjectResourceRequestSerializer(many=True)},
    )
    def get(self, request):
        qs = _resource_requests_visible_to_user(request.user)
        return Response({"results": ProjectResourceRequestSerializer(qs, many=True).data})


class ProjectResourceRequestResolveView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    @extend_schema(
        operation_id="projectResourceRequestResolve",
        request=None,
        responses={204: OpenApiResponse(description="Request marked closed")},
    )
    def post(self, request, request_id: int):
        req = generics.get_object_or_404(
            ProjectResourceRequest.objects.select_related("project"),
            pk=request_id,
            status=ProjectResourceRequest.STATUS_OPEN,
        )
        if not _user_can_resolve_resource_request(request.user, req):
            raise PermissionDenied("You cannot resolve this request.")
        req.status = ProjectResourceRequest.STATUS_CLOSED
        req.closed_at = timezone.now()
        req.resolved_by = request.user
        req.save(update_fields=["status", "closed_at", "resolved_by"])
        emit_audit_event(
            request,
            event_type="project.resource_request_resolved",
            entity_type="project_resource_request",
            action="update",
            entity_id=str(req.pk),
            project_id=str(req.project_id),
            payload={},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
