"""Serializers for ``/api/v1/departments`` (department workspace foundation)."""

from __future__ import annotations

from rest_framework import serializers

from apps.orgstructure.models import OrgUnit, OrgUnitMember
from apps.projects.models import Project


class DepartmentListSerializer(serializers.ModelSerializer):
    """List card with effective access level (from precomputed context)."""

    organization_id = serializers.IntegerField(source="organization.id", read_only=True)
    access_level = serializers.SerializerMethodField()

    class Meta:
        model = OrgUnit
        fields = ("id", "organization_id", "name", "code", "is_active", "access_level")

    def get_access_level(self, obj: OrgUnit) -> str:
        decisions = self.context.get("department_decisions") or {}
        d = decisions.get(obj.pk)
        return getattr(d, "access_level", "none") if d is not None else "none"


class DepartmentDetailSerializer(serializers.ModelSerializer):
    organization_id = serializers.IntegerField(source="organization.id", read_only=True)
    access_level = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()

    class Meta:
        model = OrgUnit
        fields = (
            "id",
            "organization_id",
            "parent_id",
            "name",
            "code",
            "description",
            "is_active",
            "created_at",
            "access_level",
        )

    def get_access_level(self, obj: OrgUnit) -> str:
        d = self.context.get("department_decision")
        return getattr(d, "access_level", "none") if d is not None else "none"

    def get_description(self, obj: OrgUnit) -> str:
        d = self.context.get("department_decision")
        if d is not None and getattr(d, "access_level", "") == "metadata":
            return ""
        return obj.description or ""


class DepartmentPatchSerializer(serializers.ModelSerializer):
    """Partial update of department fields (``department.update``)."""

    parent_id = serializers.PrimaryKeyRelatedField(
        queryset=OrgUnit.objects.all(),
        source="parent",
        allow_null=True,
        required=False,
    )

    class Meta:
        model = OrgUnit
        fields = ("name", "code", "description", "parent_id", "is_active")
        extra_kwargs = {
            "name": {"required": False},
            "code": {"required": False},
            "description": {"required": False},
            "is_active": {"required": False},
        }

    def validate_name(self, value: str):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Name may not be empty.")
        inst = self.instance
        if inst is None:
            return value
        clash = (
            OrgUnit.objects.filter(organization_id=inst.organization_id, name=value)
            .exclude(pk=inst.pk)
            .exists()
        )
        if clash:
            raise serializers.ValidationError("A department with this name already exists in the organization.")
        return value

    def validate_parent_id(self, parent: OrgUnit | None):
        inst = self.instance
        if inst is None or parent is None:
            return parent
        if parent.pk == inst.pk:
            raise serializers.ValidationError("A department cannot be its own parent.")
        if parent.organization_id != inst.organization_id:
            raise serializers.ValidationError("Parent department must belong to the same organization.")
        walk: OrgUnit | None = parent
        while walk is not None:
            if walk.pk == inst.pk:
                raise serializers.ValidationError("Invalid parent: would create a cycle in the department tree.")
            walk = walk.parent
        return parent


class DepartmentEmployeeCreateSerializer(serializers.Serializer):
    """Add or upsert a member (``department.manage_members``). ``user_id`` is the employee user id."""

    user_id = serializers.IntegerField(min_value=1)
    position = serializers.CharField(required=False, allow_blank=True, max_length=255, default="")
    is_lead = serializers.BooleanField(required=False, default=False)


class DepartmentEmployeeSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = OrgUnitMember
        fields = ("id", "user_id", "username", "position", "is_lead", "joined_at")


class DepartmentProjectStubSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ("id", "name", "code", "status")
