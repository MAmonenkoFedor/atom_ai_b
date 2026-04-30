from typing import Any

from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.organizations.models import Organization, OrganizationMember
from apps.orgstructure.models import OrgUnit
from apps.projects.models import Project, ProjectMember, ProjectResourceRequest
from apps.projects.project_permissions import (
    ProjectAccessContext,
    can_manage_project,
    project_capabilities,
)


def _project_access_context(
    serializer_context: dict,
    user,
    *,
    projects: object | None = None,
) -> ProjectAccessContext | None:
    """Pick up (or lazily create) a per-request access context.

    Views can pre-build the context for a list of projects (via
    ``context["project_access_context"] = ProjectAccessContext(user, qs)``)
    to avoid N+1 when ``many=True``. When absent we make a one-off context
    so the helper still works.

    The ``projects`` arg lets us "prime" an existing context with extra
    rows discovered later (e.g. when the ListSerializer hands us its
    iterable in ``to_representation``).
    """

    if not user or not getattr(user, "is_authenticated", False):
        return None
    ctx = serializer_context.get("project_access_context")
    if isinstance(ctx, ProjectAccessContext):
        if projects:
            ctx._load_project_grants(list(projects))  # noqa: SLF001 — same module owner
        return ctx
    ctx = ProjectAccessContext(user, projects)
    serializer_context["project_access_context"] = ctx
    return ctx

User = get_user_model()

_MISSING = object()


class ProjectSerializer(serializers.ModelSerializer):
    organization_id = serializers.IntegerField(source="organization.id", read_only=True)
    owner_id = serializers.IntegerField(source="created_by_id", read_only=True)
    owner_name = serializers.SerializerMethodField()
    primary_org_unit_id = serializers.IntegerField(read_only=True, allow_null=True)
    primary_org_unit_name = serializers.CharField(
        source="primary_org_unit.name",
        read_only=True,
        allow_null=True,
    )
    context_counts = serializers.SerializerMethodField()
    my_project_role = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()
    capabilities = serializers.SerializerMethodField()
    access_source = serializers.SerializerMethodField()
    project_lead_id = serializers.SerializerMethodField()
    project_lead = serializers.SerializerMethodField()
    project_lead_email = serializers.SerializerMethodField()
    lead_bundle_permissions = serializers.SerializerMethodField()
    lead_history = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = (
            "id",
            "organization_id",
            "code",
            "name",
            "description",
            "status",
            "owner_id",
            "owner_name",
            "primary_org_unit_id",
            "primary_org_unit_name",
            "created_at",
            "updated_at",
            "context_counts",
            "my_project_role",
            "can_manage",
            "capabilities",
            "access_source",
            "project_lead_id",
            "project_lead",
            "project_lead_email",
            "lead_bundle_permissions",
            "lead_history",
        )

    def to_representation(self, instance):
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        if (
            user is not None
            and getattr(user, "is_authenticated", False)
            and not isinstance(self.context.get("project_access_context"), ProjectAccessContext)
        ):
            iterable: object | None = None
            parent = getattr(self, "parent", None)
            if parent is not None and isinstance(parent.instance, (list, tuple)):
                iterable = parent.instance
            elif parent is not None and parent.instance is not None:
                try:
                    iterable = list(parent.instance)
                except TypeError:
                    iterable = None
            if iterable is None:
                iterable = [instance]
            _project_access_context(self.context, user, projects=iterable)
        return super().to_representation(instance)

    def get_owner_name(self, obj: Project) -> str:
        u = obj.created_by
        if not u:
            return ""
        return (u.get_full_name() or u.username or "").strip()

    def get_context_counts(self, obj: Project) -> dict:
        task_counts_map = self.context.get("project_task_counts") or {}
        project_id = int(getattr(obj, "pk", 0) or 0)
        task_counts = task_counts_map.get(project_id) or {}
        tasks_total = int(task_counts.get("tasks_total", 0))
        tasks_open = int(task_counts.get("tasks_open", 0))

        docs = getattr(obj, "_documents_total", _MISSING)
        chats = getattr(obj, "_chats_total", _MISSING)
        return {
            "tasks_total": tasks_total,
            "tasks_open": tasks_open,
            "documents_total": int(docs) if docs is not _MISSING else 0,
            "chat_threads_total": int(chats) if chats is not _MISSING else 0,
        }

    def get_my_project_role(self, obj: Project) -> str | None:
        annotated = getattr(obj, "_my_project_role", _MISSING)
        if annotated is not _MISSING:
            return annotated
        request = self.context.get("request")
        if not request or not getattr(request, "user", None) or not request.user.is_authenticated:
            return None
        m = ProjectMember.objects.filter(
            project=obj,
            user=request.user,
            is_active=True,
        ).first()
        return m.role if m else None

    def get_can_manage(self, obj: Project) -> bool:
        request = self.context.get("request")
        if not request or not getattr(request, "user", None) or not request.user.is_authenticated:
            return False
        ctx = _project_access_context(self.context, request.user)
        if ctx is not None:
            return ctx.can_manage_project(obj)
        return can_manage_project(request.user, obj)

    def get_capabilities(self, obj: Project) -> dict:
        request = self.context.get("request")
        if not request or not getattr(request, "user", None) or not request.user.is_authenticated:
            return {}
        ctx = _project_access_context(self.context, request.user)
        if ctx is not None:
            return ctx.capabilities(obj)
        return project_capabilities(request.user, obj)

    def get_access_source(self, obj: Project) -> dict | None:
        """Return source attribution only when the caller asks for it.

        Enabled by ``?include=access_source`` to keep the default payload
        small and to avoid leaking grant ids to non-admin clients.
        """

        request = self.context.get("request")
        if not request or not getattr(request, "user", None) or not request.user.is_authenticated:
            return None
        include = (request.query_params.get("include") or "") if hasattr(request, "query_params") else ""
        if "access_source" not in {part.strip() for part in include.split(",") if part.strip()}:
            return None
        ctx = _project_access_context(self.context, request.user)
        if ctx is None:
            return None
        return ctx.access_source(obj)

    def _lead_payload(self, obj: Project) -> dict:
        raw = self.context.get("project_lead_payload")
        if isinstance(raw, dict):
            return raw.get(obj.pk) or {}
        return {}

    def get_project_lead_id(self, obj: Project) -> str:
        return self._lead_payload(obj).get("project_lead_id")

    def get_project_lead(self, obj: Project) -> str:
        return self._lead_payload(obj).get("project_lead") or "-"

    def get_project_lead_email(self, obj: Project) -> str:
        return self._lead_payload(obj).get("project_lead_email") or ""

    def get_lead_bundle_permissions(self, obj: Project) -> list[str]:
        return self._lead_payload(obj).get("lead_bundle_permissions") or []

    def get_lead_history(self, obj: Project) -> list[dict[str, Any]]:
        return self._lead_payload(obj).get("lead_history") or []


class ProjectCreateSerializer(serializers.ModelSerializer):
    organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(),
        required=False,
    )
    primary_org_unit = serializers.PrimaryKeyRelatedField(
        queryset=OrgUnit.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Project
        fields = ("organization", "name", "description", "status", "code", "primary_org_unit")
        validators = []

    def validate(self, attrs):
        """
        SPA sends camelCase demo fields (ownerId, departmentId) and often omits organization.
        Default organization from the creator's active OrganizationMember; map department hints
        to primary_org_unit when possible.
        """
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None

        org = attrs.get("organization")
        if org is None and user and getattr(user, "is_authenticated", False):
            membership = (
                OrganizationMember.objects.filter(user=user, is_active=True)
                .select_related("organization")
                .order_by("-joined_at")
                .first()
            )
            if membership:
                attrs["organization"] = membership.organization

        org = attrs.get("organization")
        if org is None:
            raise serializers.ValidationError(
                {
                    "organization": (
                        "Не удалось определить организацию: у пользователя нет активного членства "
                        "в организации. Укажите organization в запросе или назначьте membership."
                    )
                }
            )

        name = str(attrs.get("name") or "").strip()
        if name and Project.objects.filter(organization=org, name=name).exists():
            raise serializers.ValidationError(
                {"name": "Проект с таким названием уже существует в этой организации."}
            )

        if attrs.get("primary_org_unit") is None:
            initial = getattr(self, "initial_data", None) or {}
            raw = None
            for key in (
                "primary_org_unit",
                "primary_org_unit_id",
                "primaryOrgUnitId",
                "department_id",
                "departmentId",
            ):
                val = initial.get(key)
                if val not in (None, ""):
                    raw = val
                    break
            resolved = self._resolve_org_unit(org, raw) if raw is not None else None
            if resolved is not None:
                attrs["primary_org_unit"] = resolved

        return attrs

    @staticmethod
    def _resolve_org_unit(organization: Organization, raw) -> OrgUnit | None:
        ref = str(raw).strip()
        if not ref:
            return None
        qs = OrgUnit.objects.filter(organization=organization, is_active=True)
        if ref.isdigit():
            hit = qs.filter(pk=int(ref)).first()
            if hit:
                return hit
        hit = qs.filter(code__iexact=ref).first()
        if hit:
            return hit
        slug = ref.removeprefix("dep-").replace("_", "-").strip()
        if slug:
            hit = qs.filter(name__iexact=slug).first()
            if hit:
                return hit
            hit = qs.filter(name__iexact=slug.replace("-", " ")).first()
            if hit:
                return hit
            hit = qs.filter(name__icontains=slug).first()
            if hit:
                return hit
        return None


class ProjectUpdateSerializer(serializers.ModelSerializer):
    primary_org_unit = serializers.PrimaryKeyRelatedField(
        queryset=OrgUnit.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Project
        fields = ("name", "description", "status", "code", "primary_org_unit")


class ProjectMemberSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    project_role = serializers.CharField(source="role", read_only=True)
    employee_id = serializers.SerializerMethodField()
    employee_name = serializers.SerializerMethodField()
    employee_role = serializers.SerializerMethodField()
    project_function = serializers.CharField(source="title_in_project", read_only=True)

    class Meta:
        model = ProjectMember
        fields = (
            "id",
            "project",
            "user_id",
            "username",
            "email",
            "first_name",
            "last_name",
            "employee_id",
            "employee_name",
            "employee_role",
            "project_function",
            "project_role",
            "is_lead",
            "engagement_weight",
            "contribution_note",
            "is_active",
            "joined_at",
        )

    def get_employee_id(self, obj: ProjectMember) -> str:
        return str(obj.user_id)

    def get_employee_name(self, obj: ProjectMember) -> str:
        u = obj.user
        return (u.get_full_name() or u.username or "").strip()

    def get_employee_role(self, obj: ProjectMember) -> str:
        return (obj.title_in_project or "").strip()


class ProjectMemberCreateSerializer(serializers.ModelSerializer):
    project_function = serializers.CharField(
        source="title_in_project",
        required=False,
        allow_blank=True,
        max_length=255,
    )

    class Meta:
        model = ProjectMember
        fields = (
            "user",
            "role",
            "project_function",
            "is_active",
            "engagement_weight",
            "contribution_note",
        )


class ProjectMemberUpdateSerializer(serializers.ModelSerializer):
    project_function = serializers.CharField(
        source="title_in_project",
        required=False,
        allow_blank=True,
        max_length=255,
    )

    class Meta:
        model = ProjectMember
        fields = ("role", "project_function", "is_active", "engagement_weight", "contribution_note")


class ProjectMemberCandidateSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    full_name = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)
    department_id = serializers.IntegerField(allow_null=True)
    department_name = serializers.CharField(allow_blank=True)


class ProjectDocumentLinkCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=500)
    url = serializers.URLField()


class ProjectResourceRequestCreateSerializer(serializers.Serializer):
    message = serializers.CharField(min_length=1, max_length=10000)


class ProjectResourceRequestSerializer(serializers.ModelSerializer):
    project_id = serializers.IntegerField(read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True)
    requested_by_id = serializers.IntegerField(source="created_by_id", read_only=True)
    requested_by_email = serializers.CharField(source="created_by.email", read_only=True)
    requested_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ProjectResourceRequest
        fields = (
            "id",
            "project_id",
            "project_name",
            "message",
            "status",
            "created_at",
            "requested_by_id",
            "requested_by_email",
            "requested_by_name",
        )

    def get_requested_by_name(self, obj: ProjectResourceRequest) -> str:
        u = obj.created_by
        return (u.get_full_name() or u.username or "").strip()
