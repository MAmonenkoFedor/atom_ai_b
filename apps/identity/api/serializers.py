from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.organizations.models import OrganizationMember
from apps.orgstructure.models import OrgUnitMember, UserManagerLink
from apps.projects.models import ProjectMember

User = get_user_model()


class EmployeeSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "is_active",
            "date_joined",
        )

    def get_full_name(self, obj):
        return obj.get_full_name().strip()


class MeSerializer(EmployeeSerializer):
    organizations = serializers.SerializerMethodField()

    class Meta(EmployeeSerializer.Meta):
        fields = EmployeeSerializer.Meta.fields + ("organizations",)

    def get_organizations(self, obj):
        memberships = (
            OrganizationMember.objects.select_related("organization")
            .filter(user=obj, is_active=True)
            .order_by("organization__name")
        )
        return [
            {
                "id": member.organization_id,
                "name": member.organization.name,
                "slug": member.organization.slug,
                "job_title": member.job_title,
            }
            for member in memberships
        ]


class AuthLoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField()

    def validate(self, attrs):
        username = attrs.get("username", "").strip()
        email = attrs.get("email", "").strip()
        if not username and not email:
            raise serializers.ValidationError(
                {"detail": "Provide either username or email."}
            )
        return attrs


class ChangeOwnPasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8, max_length=128)


class InviteActivateSerializer(serializers.Serializer):
    invite_token = serializers.CharField(required=False, allow_blank=True)
    token = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        token = (attrs.get("invite_token") or attrs.get("token") or "").strip()
        if not token:
            raise serializers.ValidationError(
                {"detail": "Invite token is required."}
            )
        attrs["resolved_token"] = token
        return attrs


class SessionUserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()
    department_id = serializers.SerializerMethodField()
    job_title = serializers.SerializerMethodField()
    position = serializers.SerializerMethodField()
    is_department_lead = serializers.SerializerMethodField()
    manager_name = serializers.SerializerMethodField()
    manager_id = serializers.SerializerMethodField()
    project_leads = serializers.SerializerMethodField()
    project_memberships = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "name",
            "email",
            "role",
            "department",
            "department_id",
            "job_title",
            "position",
            "is_department_lead",
            "manager_name",
            "manager_id",
            "project_leads",
            "project_memberships",
        )

    def _org_unit_membership(self, obj: User):
        if not hasattr(self, "_cached_org_unit_member"):
            self._cached_org_unit_member = (
                OrgUnitMember.objects.filter(user=obj)
                .select_related("org_unit", "org_unit__organization")
                .order_by("-joined_at")
                .first()
            )
        return self._cached_org_unit_member

    def _organization_member(self, obj: User):
        if not hasattr(self, "_cached_organization_member"):
            self._cached_organization_member = (
                OrganizationMember.objects.filter(user=obj, is_active=True)
                .select_related("organization")
                .order_by("-joined_at")
                .first()
            )
        return self._cached_organization_member

    def get_name(self, obj) -> str:
        full_name = obj.get_full_name().strip()
        return full_name or obj.username

    def get_role(self, obj) -> str:
        assignment = obj.role_assignments.select_related("role").first()
        if not assignment:
            return "employee"
        role_code = assignment.role.code
        if role_code == "admin":
            return "company_admin"
        if role_code in {"ceo", "executive"}:
            return "executive"
        if role_code in {"employee", "manager", "company_admin", "super_admin"}:
            return role_code
        return "employee"

    def get_department(self, obj) -> str:
        m = self._org_unit_membership(obj)
        if m and m.org_unit:
            return m.org_unit.name
        return ""

    def get_department_id(self, obj):
        m = self._org_unit_membership(obj)
        return m.org_unit_id if m else None

    def get_job_title(self, obj) -> str:
        om = self._organization_member(obj)
        if om and (om.job_title or "").strip():
            return (om.job_title or "").strip()
        return ""

    def get_position(self, obj) -> str:
        m = self._org_unit_membership(obj)
        if m and (m.position or "").strip():
            return (m.position or "").strip()
        return ""

    def get_is_department_lead(self, obj) -> bool:
        m = self._org_unit_membership(obj)
        return bool(m and m.is_lead)

    def get_manager_name(self, obj) -> str:
        om = self._organization_member(obj)
        if not om:
            return ""
        link = (
            UserManagerLink.objects.filter(employee=obj, organization=om.organization)
            .select_related("manager")
            .first()
        )
        if not link or not link.manager:
            return ""
        return (link.manager.get_full_name() or link.manager.username or "").strip()

    def get_manager_id(self, obj):
        om = self._organization_member(obj)
        if not om:
            return None
        link = UserManagerLink.objects.filter(employee=obj, organization=om.organization).first()
        return link.manager_id if link else None

    def _project_memberships(self, obj):
        if not hasattr(self, "_cached_project_memberships"):
            self._cached_project_memberships = list(
                ProjectMember.objects.filter(user=obj, is_active=True)
                .select_related("project")
                .order_by("-joined_at")
            )
        return self._cached_project_memberships

    def get_project_leads(self, obj):
        leads = [
            m
            for m in self._project_memberships(obj)
            if getattr(m, "is_lead", False) or m.role == ProjectMember.ROLE_LEAD
        ]
        return [
            {
                "project_id": str(m.project_id),
                "project_name": m.project.name,
                "title_in_project": m.title_in_project or "",
            }
            for m in leads
        ]

    def get_project_memberships(self, obj):
        return [
            {
                "project_id": str(m.project_id),
                "project_name": m.project.name,
                "project_role": m.role,
                "title_in_project": m.title_in_project or "",
            }
            for m in self._project_memberships(obj)
        ]


class SessionPayloadSerializer(serializers.Serializer):
    token = serializers.CharField()
    user = SessionUserSerializer()


class SessionResponseSerializer(serializers.Serializer):
    session = SessionPayloadSerializer()


class InviteActivateResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
    invite_token = serializers.CharField()
