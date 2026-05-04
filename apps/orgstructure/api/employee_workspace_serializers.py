"""Serializers for employee profile/workspace foundation endpoints."""

from __future__ import annotations

from rest_framework import serializers


class EmployeeListItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    full_name = serializers.CharField()
    email = serializers.CharField()
    job_title = serializers.CharField()
    access_level = serializers.CharField()


class EmployeeDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    full_name = serializers.CharField()
    email = serializers.CharField()
    access_level = serializers.CharField()
    organizations = serializers.ListField(child=serializers.DictField(), default=list)
    viewer_job_title = serializers.CharField(required=False, allow_blank=True)


class EmployeePatchSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    job_title = serializers.CharField(required=False, allow_blank=True, max_length=255)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class EmployeeRoleSerializer(serializers.Serializer):
    system_role = serializers.CharField()
    assigned_at = serializers.DateTimeField(allow_null=True)


class EmployeeRoleUpdateSerializer(serializers.Serializer):
    system_role = serializers.CharField(max_length=64)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class EmployeePermissionGrantSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    permission_code = serializers.CharField()
    scope_type = serializers.CharField()
    scope_id = serializers.CharField(allow_blank=True)
    grant_mode = serializers.CharField()
    status = serializers.CharField()
    expires_at = serializers.DateTimeField(allow_null=True)


class EmployeePermissionGrantCreateSerializer(serializers.Serializer):
    permission_code = serializers.CharField(max_length=128)
    scope_type = serializers.CharField(max_length=32, required=False, default="employee")
    scope_id = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    grant_mode = serializers.ChoiceField(
        choices=("use_only", "use_and_delegate"),
        default="use_only",
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class EmployeePermissionGrantRevokeSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class EmployeeDepartmentSerializer(serializers.Serializer):
    department_id = serializers.IntegerField()
    department_name = serializers.CharField()
    position = serializers.CharField()
    is_lead = serializers.BooleanField()
    joined_at = serializers.DateTimeField(allow_null=True)


class EmployeeProjectSerializer(serializers.Serializer):
    project_id = serializers.IntegerField()
    project_name = serializers.CharField()
    project_role = serializers.CharField()
    title_in_project = serializers.CharField()
    is_active = serializers.BooleanField()
    joined_at = serializers.DateTimeField(allow_null=True)


class EmployeeWorkspaceSerializer(serializers.Serializer):
    employee_id = serializers.IntegerField()
    access_level = serializers.CharField()
    policy = serializers.DictField()
    workspace = serializers.DictField(allow_null=True)
