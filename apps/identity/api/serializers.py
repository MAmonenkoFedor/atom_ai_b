from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.organizations.models import OrganizationMember
from apps.orgstructure.models import OrgUnitMember

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

    class Meta:
        model = User
        fields = ("id", "name", "email", "role", "department")

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
        if role_code in {"employee", "manager", "company_admin", "super_admin"}:
            return role_code
        return "employee"

    def get_department(self, obj) -> str:
        membership = (
            OrgUnitMember.objects.select_related("org_unit")
            .filter(user=obj)
            .order_by("-joined_at")
            .first()
        )
        if membership:
            return membership.org_unit.name
        return ""


class SessionPayloadSerializer(serializers.Serializer):
    token = serializers.CharField()
    user = SessionUserSerializer()


class SessionResponseSerializer(serializers.Serializer):
    session = SessionPayloadSerializer()


class InviteActivateResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
    invite_token = serializers.CharField()
