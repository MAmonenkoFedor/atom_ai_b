from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.projects.models import Project, ProjectMember

User = get_user_model()


class ProjectSerializer(serializers.ModelSerializer):
    organization_id = serializers.IntegerField(source="organization.id", read_only=True)
    created_by_id = serializers.IntegerField(source="created_by.id", read_only=True)

    class Meta:
        model = Project
        fields = (
            "id",
            "organization_id",
            "name",
            "description",
            "status",
            "created_by_id",
            "created_at",
            "updated_at",
        )


class ProjectCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ("organization", "name", "description", "status")


class ProjectUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ("name", "description", "status")


class ProjectMemberSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)

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
            "role",
            "is_active",
            "joined_at",
        )


class ProjectMemberCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectMember
        fields = ("user", "role", "is_active")


class ProjectMemberUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectMember
        fields = ("role", "is_active")
