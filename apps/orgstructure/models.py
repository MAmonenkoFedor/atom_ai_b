from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class OrgUnit(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="units",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="children",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "name"),
                name="uniq_org_unit_name_per_org",
            )
        ]
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class OrgUnitMember(models.Model):
    org_unit = models.ForeignKey(
        OrgUnit,
        on_delete=models.CASCADE,
        related_name="members",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="org_unit_memberships",
    )
    position = models.CharField(max_length=255, blank=True)
    is_lead = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("org_unit", "user"),
                name="uniq_org_unit_member",
            )
        ]
        ordering = ("-is_lead", "user_id")

    def __str__(self) -> str:
        return f"{self.org_unit_id}:{self.user_id}"


class UserManagerLink(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="manager_links",
    )
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="manager_links",
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="direct_reports_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "employee"),
                name="uniq_manager_link_per_employee_org",
            )
        ]
        ordering = ("employee_id",)

    def clean(self):
        if self.employee_id and self.employee_id == self.manager_id:
            raise ValidationError("Employee cannot be their own manager.")

    def __str__(self) -> str:
        return f"{self.organization_id}:{self.employee_id}->{self.manager_id}"
