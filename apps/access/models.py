"""Core models for the access-control service.

Everything in this module is *data* only — business logic lives in
:mod:`apps.access.resolver` and :mod:`apps.access.service`. Views / other
apps should never write to these tables directly.

Architectural formula (v1):

    Employee              = apps.identity (User)
    PermissionDefinition  = what permissions exist in the system
    PermissionGrant       = a concrete grant: employee X has code Y in scope Z
    RoleTemplate          = a named bundle of permissions
    RoleTemplatePermission= permissions inside a template
    RoleTemplateAssignment= a template applied to an employee (in a scope)
    DelegationRule        = whether / how a permission may be re-delegated
    PermissionAuditLog    = journal of every grant / revoke / delegate event
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


# ---------------------------------------------------------------------------
# Shared scope vocabulary
# ---------------------------------------------------------------------------

SCOPE_GLOBAL = "global"
SCOPE_COMPANY = "company"
SCOPE_DEPARTMENT = "department"
SCOPE_PROJECT = "project"
SCOPE_TASK = "task"
SCOPE_AI_WORKSPACE = "ai_workspace"
SCOPE_MODULE = "module"
SCOPE_SELF = "self"

SCOPE_CHOICES = (
    (SCOPE_GLOBAL, "Global"),
    (SCOPE_COMPANY, "Company"),
    (SCOPE_DEPARTMENT, "Department"),
    (SCOPE_PROJECT, "Project"),
    (SCOPE_TASK, "Task"),
    (SCOPE_AI_WORKSPACE, "AI workspace"),
    (SCOPE_MODULE, "Module"),
    (SCOPE_SELF, "Self"),
)

# Ordering used for "scope ⊇ scope" comparisons (lower index = broader).
SCOPE_BREADTH_ORDER = {
    SCOPE_GLOBAL: 0,
    SCOPE_COMPANY: 1,
    SCOPE_DEPARTMENT: 2,
    SCOPE_PROJECT: 2,
    SCOPE_MODULE: 2,
    SCOPE_TASK: 3,
    SCOPE_AI_WORKSPACE: 3,
    SCOPE_SELF: 4,
}


# ---------------------------------------------------------------------------
# Permission definitions (catalog)
# ---------------------------------------------------------------------------


class PermissionDefinition(models.Model):
    """The catalog of all permissions recognised by the platform.

    ``code`` is the canonical machine-readable key. Examples:
    ``project.create``, ``docs.upload``, ``rights.grant``.
    """

    MODULE_ORGANIZATION = "organization"
    MODULE_PROJECTS = "projects"
    MODULE_DOCUMENTS = "documents"
    MODULE_TASKS = "tasks"
    MODULE_AI = "ai"
    MODULE_ACCESS = "access"
    MODULE_OTHER = "other"

    MODULE_CHOICES = (
        (MODULE_ORGANIZATION, "Organization"),
        (MODULE_PROJECTS, "Projects"),
        (MODULE_DOCUMENTS, "Documents"),
        (MODULE_TASKS, "Tasks"),
        (MODULE_AI, "AI"),
        (MODULE_ACCESS, "Access"),
        (MODULE_OTHER, "Other"),
    )

    code = models.CharField(max_length=128, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    module = models.CharField(max_length=32, choices=MODULE_CHOICES, default=MODULE_OTHER)

    # Allowed scope types for this permission. Stored as a JSON list of strings
    # (subset of SCOPE_CHOICES). At least one entry is required.
    allowed_scopes = models.JSONField(default=list, blank=True)

    # Whether this permission may be re-delegated by a holder (subject to the
    # matching :class:`DelegationRule`).
    can_be_delegated = models.BooleanField(default=False)

    # Sensitive permissions surface a warning in the UI and are never picked up
    # by cascading / inheritance helpers (v1 has no inheritance anyway).
    is_sensitive = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("module", "code")
        indexes = [
            models.Index(fields=("module", "code")),
            models.Index(fields=("is_active",)),
        ]

    def __str__(self) -> str:
        return self.code


# ---------------------------------------------------------------------------
# Role templates
# ---------------------------------------------------------------------------


class RoleTemplate(models.Model):
    """A named bundle of permissions that can be applied to an employee.

    Templates are *convenience* — the source of truth for whether a user holds
    a permission is still :class:`PermissionGrant` combined with
    :class:`RoleTemplateAssignment`. Assigning a template effectively says
    "all ``default_enabled=True`` permissions inside this template are granted
    to the employee in the assignment's scope, via source_type=role_template".
    """

    code = models.CharField(max_length=128, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    # Default scope type used when assigning this template (the operator can
    # override on assignment).
    default_scope_type = models.CharField(
        max_length=32, choices=SCOPE_CHOICES, default=SCOPE_GLOBAL
    )

    # ``is_system`` templates are created by seeds and cannot be deleted from
    # the UI — only deactivated.
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("code",)

    def __str__(self) -> str:
        return self.code


class RoleTemplatePermission(models.Model):
    """A single permission inside a role template."""

    GRANT_MODE_USE_ONLY = "use_only"
    GRANT_MODE_USE_AND_DELEGATE = "use_and_delegate"
    GRANT_MODE_CHOICES = (
        (GRANT_MODE_USE_ONLY, "Use only"),
        (GRANT_MODE_USE_AND_DELEGATE, "Use and delegate"),
    )

    role_template = models.ForeignKey(
        RoleTemplate,
        on_delete=models.CASCADE,
        related_name="permissions",
    )
    permission_code = models.CharField(max_length=128)
    grant_mode = models.CharField(
        max_length=32,
        choices=GRANT_MODE_CHOICES,
        default=GRANT_MODE_USE_ONLY,
    )
    default_enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("role_template", "permission_code"),
                name="uniq_role_template_permission",
            )
        ]
        indexes = [models.Index(fields=("permission_code",))]
        ordering = ("permission_code",)

    def __str__(self) -> str:
        return f"{self.role_template.code}:{self.permission_code}"


class RoleTemplateAssignment(models.Model):
    """An assignment of a role template to a specific employee in a scope."""

    role_template = models.ForeignKey(
        RoleTemplate, on_delete=models.CASCADE, related_name="assignments"
    )
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="access_role_templates",
    )
    scope_type = models.CharField(max_length=32, choices=SCOPE_CHOICES, default=SCOPE_GLOBAL)
    scope_id = models.CharField(max_length=128, blank=True, default="")

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_role_templates",
    )
    note = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=("employee", "is_active")),
            models.Index(fields=("role_template", "is_active")),
            models.Index(fields=("scope_type", "scope_id")),
        ]
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.employee_id}:{self.role_template.code}@{self.scope_type}:{self.scope_id}"


# ---------------------------------------------------------------------------
# Direct permission grants
# ---------------------------------------------------------------------------


class PermissionGrant(models.Model):
    """The atomic fact: employee X has permission Y in scope Z.

    Multiple grants for the same (employee, permission, scope) are allowed on
    purpose — we never hide history behind overwrites. The resolver coalesces
    them by ``status`` + ``grant_mode``.
    """

    STATUS_ACTIVE = "active"
    STATUS_REVOKED = "revoked"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Active"),
        (STATUS_REVOKED, "Revoked"),
        (STATUS_EXPIRED, "Expired"),
    )

    GRANT_MODE_USE_ONLY = "use_only"
    GRANT_MODE_USE_AND_DELEGATE = "use_and_delegate"
    GRANT_MODE_CHOICES = (
        (GRANT_MODE_USE_ONLY, "Use only"),
        (GRANT_MODE_USE_AND_DELEGATE, "Use and delegate"),
    )

    SOURCE_MANUAL = "manual"
    SOURCE_ROLE_TEMPLATE = "role_template"
    SOURCE_DELEGATION = "delegation"
    SOURCE_SYSTEM_SEED = "system_seed"
    SOURCE_CHOICES = (
        (SOURCE_MANUAL, "Manual"),
        (SOURCE_ROLE_TEMPLATE, "Role template"),
        (SOURCE_DELEGATION, "Delegation"),
        (SOURCE_SYSTEM_SEED, "System seed"),
    )

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="access_grants",
    )

    # We link by string ``code`` instead of FK to keep grants resilient when
    # permission definitions evolve. Deactivating the definition will simply
    # make the grant irrelevant to the resolver.
    permission_code = models.CharField(max_length=128)

    scope_type = models.CharField(max_length=32, choices=SCOPE_CHOICES, default=SCOPE_GLOBAL)
    scope_id = models.CharField(max_length=128, blank=True, default="")

    grant_mode = models.CharField(
        max_length=32,
        choices=GRANT_MODE_CHOICES,
        default=GRANT_MODE_USE_ONLY,
    )

    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="issued_access_grants",
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revoked_access_grants",
    )

    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE
    )
    note = models.TextField(blank=True)

    # Delegation chain — parent_grant is the grant that authorised this one.
    parent_grant = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="delegated_grants",
    )

    source_type = models.CharField(
        max_length=32, choices=SOURCE_CHOICES, default=SOURCE_MANUAL
    )
    # Optional pointer to whatever created the grant
    # (role_template id, parent grant id, migration name, …).
    source_id = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=("employee", "status")),
            models.Index(fields=("permission_code", "status")),
            models.Index(fields=("scope_type", "scope_id")),
            models.Index(fields=("parent_grant",)),
        ]
        ordering = ("-granted_at",)

    def __str__(self) -> str:
        return (
            f"{self.employee_id}:{self.permission_code}@{self.scope_type}:{self.scope_id}"
            f"/{self.status}"
        )

    @property
    def is_active(self) -> bool:
        return self.status == self.STATUS_ACTIVE


class PermissionDeny(models.Model):
    """Explicit deny rule for a user/permission/scope.

    Deny entries are checked before grants in the resolver:
        deny > allow
    """

    STATUS_ACTIVE = "active"
    STATUS_REVOKED = "revoked"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Active"),
        (STATUS_REVOKED, "Revoked"),
        (STATUS_EXPIRED, "Expired"),
    )

    SOURCE_MANUAL = "manual"
    SOURCE_POLICY = "policy"
    SOURCE_SYSTEM = "system"
    SOURCE_CHOICES = (
        (SOURCE_MANUAL, "Manual"),
        (SOURCE_POLICY, "Policy"),
        (SOURCE_SYSTEM, "System"),
    )

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="access_denies",
    )
    permission_code = models.CharField(max_length=128)
    scope_type = models.CharField(max_length=32, choices=SCOPE_CHOICES, default=SCOPE_GLOBAL)
    scope_id = models.CharField(max_length=128, blank=True, default="")

    denied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="issued_access_denies",
    )
    denied_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revoked_access_denies",
    )

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    source_type = models.CharField(max_length=32, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    source_id = models.CharField(max_length=128, blank=True, default="")
    note = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=("employee", "status")),
            models.Index(fields=("permission_code", "status")),
            models.Index(fields=("scope_type", "scope_id")),
        ]
        ordering = ("-denied_at",)

    def __str__(self) -> str:
        return (
            f"DENY:{self.employee_id}:{self.permission_code}"
            f"@{self.scope_type}:{self.scope_id}/{self.status}"
        )


# ---------------------------------------------------------------------------
# Delegation rules
# ---------------------------------------------------------------------------


class DelegationRule(models.Model):
    """Declarative rules that constrain how a permission may be re-delegated.

    When a user with ``use_and_delegate`` attempts to issue a new grant, the
    resolver loads the matching rule (by permission_code and scope transition)
    and rejects the attempt if any of these conditions fails:

    * ``allow_delegate`` is False;
    * the target scope is *broader* than the delegator's own grant scope;
    * ``max_delegate_depth`` is exceeded by the parent chain.
    """

    permission_code = models.CharField(max_length=128)
    from_scope_type = models.CharField(max_length=32, choices=SCOPE_CHOICES)
    to_scope_type = models.CharField(max_length=32, choices=SCOPE_CHOICES)

    allow_delegate = models.BooleanField(default=True)
    allow_same_scope_only = models.BooleanField(default=False)
    allow_narrower_scope = models.BooleanField(default=True)
    max_delegate_depth = models.PositiveSmallIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("permission_code", "from_scope_type", "to_scope_type"),
                name="uniq_delegation_rule",
            )
        ]
        indexes = [
            models.Index(fields=("permission_code",)),
            models.Index(fields=("from_scope_type", "to_scope_type")),
        ]
        ordering = ("permission_code", "from_scope_type", "to_scope_type")

    def __str__(self) -> str:
        return (
            f"{self.permission_code}:{self.from_scope_type}->{self.to_scope_type}"
            f"({'+' if self.allow_delegate else '-'})"
        )


# ---------------------------------------------------------------------------
# Audit log (dedicated for permissions — independent of generic AuditEvent)
# ---------------------------------------------------------------------------


class PermissionAuditLog(models.Model):
    """Dedicated audit stream for permission mutations.

    We log here in addition to the generic :class:`apps.audit.models.AuditEvent`
    because "who granted what to whom" is a permission-engineering question
    that needs its own, structured, queryable index.
    """

    ACTION_GRANT_CREATED = "grant_created"
    ACTION_GRANT_UPDATED = "grant_updated"
    ACTION_GRANT_REVOKED = "grant_revoked"
    ACTION_GRANT_EXPIRED = "grant_expired"
    ACTION_DELEGATE_CREATED = "delegate_created"
    ACTION_DELEGATE_REVOKED = "delegate_revoked"
    ACTION_TEMPLATE_ASSIGNED = "template_assigned"
    ACTION_TEMPLATE_REMOVED = "template_removed"
    ACTION_DEFINITION_UPDATED = "definition_updated"
    ACTION_RULE_UPDATED = "rule_updated"
    ACTION_DENY_CREATED = "deny_created"
    ACTION_DENY_REVOKED = "deny_revoked"

    ACTION_CHOICES = (
        (ACTION_GRANT_CREATED, "Grant created"),
        (ACTION_GRANT_UPDATED, "Grant updated"),
        (ACTION_GRANT_REVOKED, "Grant revoked"),
        (ACTION_GRANT_EXPIRED, "Grant expired"),
        (ACTION_DELEGATE_CREATED, "Delegate created"),
        (ACTION_DELEGATE_REVOKED, "Delegate revoked"),
        (ACTION_TEMPLATE_ASSIGNED, "Template assigned"),
        (ACTION_TEMPLATE_REMOVED, "Template removed"),
        (ACTION_DEFINITION_UPDATED, "Permission definition updated"),
        (ACTION_RULE_UPDATED, "Delegation rule updated"),
        (ACTION_DENY_CREATED, "Deny created"),
        (ACTION_DENY_REVOKED, "Deny revoked"),
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_audit_actions",
    )
    target_employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_audit_targets",
    )
    action = models.CharField(max_length=64, choices=ACTION_CHOICES)

    permission_code = models.CharField(max_length=128, blank=True, default="")
    scope_type = models.CharField(max_length=32, blank=True, default="")
    scope_id = models.CharField(max_length=128, blank=True, default="")

    # Structured before/after snapshots — kept as JSON to stay flexible.
    old_value = models.JSONField(default=dict, blank=True)
    new_value = models.JSONField(default=dict, blank=True)

    note = models.TextField(blank=True)
    request_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=("target_employee", "created_at")),
            models.Index(fields=("actor", "created_at")),
            models.Index(fields=("action",)),
            models.Index(fields=("permission_code",)),
        ]
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return f"{self.action}:{self.permission_code}@{self.scope_type}:{self.scope_id}"
