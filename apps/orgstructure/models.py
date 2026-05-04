from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import get_valid_filename


def org_unit_document_upload_to(instance: "OrgUnitDocument", filename: str) -> str:
    safe = get_valid_filename(filename)
    return f"org_unit_documents/{instance.org_unit_id}/{uuid4().hex[:10]}_{safe}"


class OrgUnit(models.Model):
    """Подразделение компании (иерархия: маркетинг, дизайн, разработка…)."""

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
    description = models.TextField(blank=True, default="")
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
    """Связь пользователь ↔ отдел (у сотрудника может не быть ни одной записи). position — роль внутри отдела; is_lead — глава отдела."""

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
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_org_unit_members",
    )

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


class OrgUnitDocument(models.Model):
    """Файлы и внешние ссылки, привязанные к отделу (department workspace documents)."""

    class Source(models.TextChoices):
        UPLOAD = "upload", "Upload"
        EXTERNAL = "external", "External link"

    org_unit = models.ForeignKey(OrgUnit, on_delete=models.CASCADE, related_name="documents")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_org_unit_documents",
    )
    title = models.CharField(max_length=500)
    document_type = models.CharField(max_length=16)
    source = models.CharField(max_length=16, choices=Source.choices)
    external_href = models.TextField(blank=True)
    file = models.FileField(upload_to=org_unit_document_upload_to, blank=True, null=True)
    storage_provider = models.ForeignKey(
        "storage.StorageProvider",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="org_unit_documents",
    )
    storage_object_key = models.TextField(blank=True, default="")
    upload_stored_bytes = models.PositiveBigIntegerField(default=0)
    owner_label = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self) -> str:
        return f"{self.org_unit_id}:{self.title[:40]}"

    def resolve_href(self, request) -> str:
        key = (self.storage_object_key or "").strip()
        if key and self.storage_provider_id:
            from apps.storage.credentials_vault import decrypt_credentials_field
            from apps.storage.s3_runtime import presigned_get_url

            prov = self.storage_provider
            if prov:
                c = decrypt_credentials_field(prov.credentials)
                if c.get("access_key") and c.get("secret_key"):
                    return presigned_get_url(
                        prov,
                        access_key=c["access_key"],
                        secret_key=c["secret_key"],
                        object_key=key,
                    )
        if self.file:
            return request.build_absolute_uri(self.file.url)
        return (self.external_href or "").strip()

    def to_api_dict(self, request) -> dict:
        ou = self.org_unit
        return {
            "id": f"ddoc-{self.pk}",
            "title": self.title,
            "type": self.document_type,
            "updated_at": self.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "owner": self.owner_label,
            "href": self.resolve_href(request),
            "department_id": str(ou.pk),
            "department_name": ou.name,
        }


class EmployeeCareerEvent(models.Model):
    """Вечная лента карьерных событий сотрудника (назначения, переводы, повышения/понижения).

    Хранится отдельно от текущих назначений (`OrgUnitMember`, `ProjectMember`) и служит единым
    источником правды для истории. Любое изменение принадлежности к отделу, статуса главы отдела,
    проектной роли, должности и т.п. пишется отдельной строкой.
    """

    EVENT_HIRED = "hired"
    EVENT_SYSTEM_ROLE_CHANGED = "system_role_changed"
    EVENT_JOB_TITLE_CHANGED = "job_title_changed"
    EVENT_JOINED_DEPARTMENT = "joined_department"
    EVENT_LEFT_DEPARTMENT = "left_department"
    EVENT_TRANSFERRED_DEPARTMENT = "transferred_department"
    EVENT_BECAME_DEPARTMENT_LEAD = "became_department_lead"
    EVENT_REMOVED_AS_DEPARTMENT_LEAD = "removed_as_department_lead"
    EVENT_POSITION_CHANGED = "position_changed"
    EVENT_ASSIGNED_TO_PROJECT = "assigned_to_project"
    EVENT_REMOVED_FROM_PROJECT = "removed_from_project"
    EVENT_PROJECT_ROLE_CHANGED = "project_role_changed"
    EVENT_BECAME_PROJECT_LEAD = "became_project_lead"
    EVENT_REMOVED_AS_PROJECT_LEAD = "removed_as_project_lead"
    EVENT_MANAGER_CHANGED = "manager_changed"
    EVENT_CHOICES = (
        (EVENT_HIRED, "Hired"),
        (EVENT_SYSTEM_ROLE_CHANGED, "System role changed"),
        (EVENT_JOB_TITLE_CHANGED, "Job title changed"),
        (EVENT_JOINED_DEPARTMENT, "Joined department"),
        (EVENT_LEFT_DEPARTMENT, "Left department"),
        (EVENT_TRANSFERRED_DEPARTMENT, "Transferred department"),
        (EVENT_BECAME_DEPARTMENT_LEAD, "Became department lead"),
        (EVENT_REMOVED_AS_DEPARTMENT_LEAD, "Removed as department lead"),
        (EVENT_POSITION_CHANGED, "Position changed"),
        (EVENT_ASSIGNED_TO_PROJECT, "Assigned to project"),
        (EVENT_REMOVED_FROM_PROJECT, "Removed from project"),
        (EVENT_PROJECT_ROLE_CHANGED, "Project role changed"),
        (EVENT_BECAME_PROJECT_LEAD, "Became project lead"),
        (EVENT_REMOVED_AS_PROJECT_LEAD, "Removed as project lead"),
        (EVENT_MANAGER_CHANGED, "Manager changed"),
    )

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="career_events",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="career_events",
    )
    event_type = models.CharField(max_length=64, choices=EVENT_CHOICES)
    from_value = models.CharField(max_length=255, blank=True)
    to_value = models.CharField(max_length=255, blank=True)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authored_career_events",
    )
    reason = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee_career_events",
    )
    org_unit = models.ForeignKey(
        OrgUnit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee_career_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-effective_from", "-id")
        indexes = [
            models.Index(fields=("employee", "-effective_from")),
            models.Index(fields=("event_type", "-effective_from")),
            models.Index(fields=("project", "-effective_from")),
            models.Index(fields=("org_unit", "-effective_from")),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id}:{self.event_type}:{self.effective_from:%Y-%m-%d}"


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
