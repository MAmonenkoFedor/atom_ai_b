from rest_framework import serializers

from apps.orgstructure.models import OrgUnit, OrgUnitMember


class OrgUnitSerializer(serializers.ModelSerializer):
    parent_id = serializers.IntegerField(source="parent.id", allow_null=True, read_only=True)
    organization_id = serializers.IntegerField(source="organization.id", read_only=True)

    class Meta:
        model = OrgUnit
        fields = (
            "id",
            "organization_id",
            "parent_id",
            "name",
            "code",
            "is_active",
            "created_at",
        )


class OrgUnitMemberSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)

    class Meta:
        model = OrgUnitMember
        fields = (
            "id",
            "org_unit",
            "user_id",
            "username",
            "email",
            "first_name",
            "last_name",
            "position",
            "is_lead",
            "joined_at",
        )
