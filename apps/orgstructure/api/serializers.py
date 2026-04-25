from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.core.api.permissions import normalized_roles_for_user
from apps.organizations.models import Organization, OrganizationMember
from apps.orgstructure.models import OrgUnit, OrgUnitMember

User = get_user_model()


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


class OrgUnitCreateSerializer(serializers.ModelSerializer):
    organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )
    parent = serializers.PrimaryKeyRelatedField(
        queryset=OrgUnit.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = OrgUnit
        fields = ("name", "code", "parent", "organization")

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        if not user or not getattr(user, "is_authenticated", False):
            raise serializers.ValidationError({"detail": "Требуется авторизация."})
        roles = normalized_roles_for_user(user)
        org = attrs.get("organization")
        if org is None:
            if "super_admin" in roles:
                raise serializers.ValidationError(
                    {"organization": "Укажите organization при создании отдела."}
                )
            membership = (
                OrganizationMember.objects.filter(user=user, is_active=True)
                .select_related("organization")
                .order_by("-joined_at")
                .first()
            )
            if not membership:
                raise serializers.ValidationError(
                    {"organization": "Нет активного членства в организации."}
                )
            attrs["organization"] = membership.organization
            org = attrs["organization"]
        else:
            if "super_admin" not in roles:
                if not OrganizationMember.objects.filter(
                    user=user, organization=org, is_active=True
                ).exists():
                    raise serializers.ValidationError(
                        {"organization": "Нет доступа к выбранной организации."}
                    )
        parent = attrs.get("parent")
        if parent is not None and parent.organization_id != org.id:
            raise serializers.ValidationError(
                {"parent": "Родительский отдел принадлежит другой организации."}
            )
        return attrs


class OrgUnitMemberUpsertSerializer(serializers.Serializer):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    is_lead = serializers.BooleanField(required=False, default=False)
    position = serializers.CharField(required=False, allow_blank=True, max_length=255, default="")
