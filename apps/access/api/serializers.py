"""Serializers for the access-control REST API."""

from __future__ import annotations

from rest_framework import serializers

from apps.access.models import (
    DelegationRule,
    PermissionAuditLog,
    PermissionDefinition,
    PermissionDeny,
    PermissionGrant,
    RoleTemplate,
    RoleTemplateAssignment,
    RoleTemplatePermission,
)


# ---------------------------------------------------------------------------
# Permission catalog
# ---------------------------------------------------------------------------


class PermissionDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PermissionDefinition
        fields = (
            "id",
            "code",
            "name",
            "description",
            "module",
            "allowed_scopes",
            "can_be_delegated",
            "is_sensitive",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")


# ---------------------------------------------------------------------------
# Role templates
# ---------------------------------------------------------------------------


class RoleTemplatePermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleTemplatePermission
        fields = ("id", "permission_code", "grant_mode", "default_enabled")


class RoleTemplateSerializer(serializers.ModelSerializer):
    permissions = RoleTemplatePermissionSerializer(many=True, read_only=True)

    class Meta:
        model = RoleTemplate
        fields = (
            "id",
            "code",
            "name",
            "description",
            "default_scope_type",
            "is_system",
            "is_active",
            "permissions",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at", "is_system", "permissions")


class RoleTemplateAssignmentSerializer(serializers.ModelSerializer):
    role_template_code = serializers.CharField(
        source="role_template.code", read_only=True
    )
    role_template_name = serializers.CharField(
        source="role_template.name", read_only=True
    )
    assigned_by_email = serializers.SerializerMethodField()

    class Meta:
        model = RoleTemplateAssignment
        fields = (
            "id",
            "role_template",
            "role_template_code",
            "role_template_name",
            "employee",
            "scope_type",
            "scope_id",
            "assigned_by",
            "assigned_by_email",
            "note",
            "is_active",
            "created_at",
            "revoked_at",
        )
        read_only_fields = ("created_at", "revoked_at", "is_active")

    @staticmethod
    def get_assigned_by_email(obj: RoleTemplateAssignment) -> str | None:
        actor = obj.assigned_by
        if actor is None:
            return None
        return getattr(actor, "email", None)


# ---------------------------------------------------------------------------
# Permission grants
# ---------------------------------------------------------------------------


class PermissionGrantSerializer(serializers.ModelSerializer):
    granted_by_email = serializers.SerializerMethodField()
    revoked_by_email = serializers.SerializerMethodField()
    employee_email = serializers.CharField(source="employee.email", read_only=True)

    class Meta:
        model = PermissionGrant
        fields = (
            "id",
            "employee",
            "employee_email",
            "permission_code",
            "scope_type",
            "scope_id",
            "grant_mode",
            "granted_by",
            "granted_by_email",
            "granted_at",
            "expires_at",
            "revoked_at",
            "revoked_by",
            "revoked_by_email",
            "status",
            "note",
            "parent_grant",
            "source_type",
            "source_id",
        )
        read_only_fields = (
            "granted_at",
            "revoked_at",
            "status",
            "granted_by",
            "revoked_by",
        )

    @staticmethod
    def get_granted_by_email(obj: PermissionGrant) -> str | None:
        actor = obj.granted_by
        return getattr(actor, "email", None) if actor else None


class PermissionDenySerializer(serializers.ModelSerializer):
    denied_by_email = serializers.SerializerMethodField()
    revoked_by_email = serializers.SerializerMethodField()
    employee_email = serializers.CharField(source="employee.email", read_only=True)

    class Meta:
        model = PermissionDeny
        fields = (
            "id",
            "employee",
            "employee_email",
            "permission_code",
            "scope_type",
            "scope_id",
            "denied_by",
            "denied_by_email",
            "denied_at",
            "expires_at",
            "revoked_at",
            "revoked_by",
            "revoked_by_email",
            "status",
            "note",
            "source_type",
            "source_id",
        )
        read_only_fields = (
            "denied_at",
            "revoked_at",
            "status",
            "denied_by",
            "revoked_by",
        )

    @staticmethod
    def get_denied_by_email(obj: PermissionDeny) -> str | None:
        actor = obj.denied_by
        return getattr(actor, "email", None) if actor else None

    @staticmethod
    def get_revoked_by_email(obj: PermissionDeny) -> str | None:
        actor = obj.revoked_by
        return getattr(actor, "email", None) if actor else None

    @staticmethod
    def get_revoked_by_email(obj: PermissionGrant) -> str | None:
        actor = obj.revoked_by
        return getattr(actor, "email", None) if actor else None


# ---------------------------------------------------------------------------
# Delegation rules
# ---------------------------------------------------------------------------


class DelegationRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DelegationRule
        fields = (
            "id",
            "permission_code",
            "from_scope_type",
            "to_scope_type",
            "allow_delegate",
            "allow_same_scope_only",
            "allow_narrower_scope",
            "max_delegate_depth",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class PermissionAuditLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.SerializerMethodField()
    target_email = serializers.SerializerMethodField()

    class Meta:
        model = PermissionAuditLog
        fields = (
            "id",
            "actor",
            "actor_email",
            "target_employee",
            "target_email",
            "action",
            "permission_code",
            "scope_type",
            "scope_id",
            "old_value",
            "new_value",
            "note",
            "request_id",
            "created_at",
        )

    @staticmethod
    def get_actor_email(obj: PermissionAuditLog) -> str | None:
        actor = obj.actor
        return getattr(actor, "email", None) if actor else None

    @staticmethod
    def get_target_email(obj: PermissionAuditLog) -> str | None:
        target = obj.target_employee
        return getattr(target, "email", None) if target else None


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


class GrantCreateSerializer(serializers.Serializer):
    employee_id = serializers.IntegerField()
    permission_code = serializers.CharField(max_length=128)
    scope_type = serializers.CharField(max_length=32)
    scope_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    grant_mode = serializers.ChoiceField(
        choices=[m[0] for m in PermissionGrant.GRANT_MODE_CHOICES],
        default=PermissionGrant.GRANT_MODE_USE_ONLY,
    )
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True)
    parent_grant_id = serializers.IntegerField(required=False, allow_null=True)


class GrantRevokeSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True)


class DenyCreateSerializer(serializers.Serializer):
    employee_id = serializers.IntegerField()
    permission_code = serializers.CharField(max_length=128)
    scope_type = serializers.CharField(max_length=32)
    scope_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True)


class DenyRevokeSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True)


class TemplateAssignSerializer(serializers.Serializer):
    role_template_id = serializers.IntegerField()
    employee_id = serializers.IntegerField()
    scope_type = serializers.CharField(max_length=32, required=False, allow_blank=True)
    scope_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)


class TemplatePermissionInputSerializer(serializers.Serializer):
    permission_code = serializers.CharField(max_length=128)
    grant_mode = serializers.ChoiceField(
        choices=[m[0] for m in RoleTemplatePermission.GRANT_MODE_CHOICES],
        default=RoleTemplatePermission.GRANT_MODE_USE_ONLY,
    )
    default_enabled = serializers.BooleanField(default=True)
