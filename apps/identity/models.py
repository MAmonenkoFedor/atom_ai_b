from django.conf import settings
from django.db import models


class Role(models.Model):
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("code",)

    def __str__(self) -> str:
        return self.code


class UserRole(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="role_assignments",
    )
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="assignments")
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="user_roles",
        null=True,
        blank=True,
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "role", "organization"),
                name="uniq_user_role_per_org",
            )
        ]
        ordering = ("-assigned_at",)

    def __str__(self) -> str:
        org = self.organization_id if self.organization_id else "global"
        return f"{self.user_id}:{self.role.code}:{org}"


class UserCapability(models.Model):
    """Explicit per-user capability grant.

    Scope values:
    - ``global`` — applies platform-wide.
    - ``org:<organization_id>`` — scoped to a single organization.
    - ``project:<project_id>`` — scoped to a single project.

    Effective capabilities for a user = role bundles ∪ explicit grants.
    """

    SCOPE_GLOBAL = "global"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="capability_grants",
    )
    capability = models.CharField(max_length=128)
    scope = models.CharField(max_length=128, default=SCOPE_GLOBAL)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_capabilities",
    )
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "capability", "scope"),
                name="uniq_user_capability_per_scope",
            )
        ]
        indexes = [
            models.Index(fields=("user", "capability")),
            models.Index(fields=("capability",)),
        ]
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.user_id}:{self.capability}@{self.scope}"
