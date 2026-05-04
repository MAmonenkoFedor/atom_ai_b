from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils.text import get_valid_filename


def project_document_upload_to(instance: "ProjectDocument", filename: str) -> str:
    safe = get_valid_filename(filename)
    return f"project_documents/{instance.project_id}/{uuid4().hex[:10]}_{safe}"


class Project(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_ON_HOLD = "on_hold"
    STATUS_COMPLETED = "completed"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Active"),
        (STATUS_ON_HOLD, "On Hold"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_ARCHIVED, "Archived"),
    )

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="projects",
    )
    """Орг-юнит компании для контекста проекта (иерархия, отчётность; не «тип» проекта)."""
    primary_org_unit = models.ForeignKey(
        "orgstructure.OrgUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_projects",
    )
    code = models.CharField(max_length=64, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    public_summary = models.TextField(blank=True, default="")
    planned_start = models.DateField(null=True, blank=True)
    planned_end = models.DateField(null=True, blank=True)
    """Structured settings (visibility, workflow, AI defaults, …) — shallow-merge on PATCH."""
    project_settings = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_projects",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "name"),
                name="uniq_project_name_per_org",
            )
        ]
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.name


class ProjectMember(models.Model):
    # Постоянные роли проекта. owner — создатель/собственник (полное управление + передача).
    # lead — руководитель проекта (manage members, tasks, docs). manager — помощник lead,
    # может редактировать состав и задачи, но не передавать владение.
    # editor / contributor — могут работать в проекте; viewer — только чтение.
    ROLE_OWNER = "owner"
    ROLE_LEAD = "lead"
    ROLE_MANAGER = "manager"
    ROLE_EDITOR = "editor"
    ROLE_CONTRIBUTOR = "contributor"
    ROLE_VIEWER = "viewer"
    ROLE_CHOICES = (
        (ROLE_OWNER, "Owner"),
        (ROLE_LEAD, "Project lead"),
        (ROLE_MANAGER, "Project manager"),
        (ROLE_EDITOR, "Editor"),
        (ROLE_CONTRIBUTOR, "Contributor"),
        (ROLE_VIEWER, "Viewer"),
    )
    MANAGE_ROLES = (ROLE_OWNER, ROLE_LEAD, ROLE_MANAGER, ROLE_EDITOR)

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_memberships",
    )
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default=ROLE_EDITOR)
    """Профессиональное название роли в проекте (напр. «Старший дизайнер»), отдельно от системной роли."""
    title_in_project = models.CharField(max_length=255, blank=True)
    """Approximate share of capacity on this project (e.g. 0.5 = half-time with another lead)."""
    engagement_weight = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        null=True,
        blank=True,
    )
    contribution_note = models.CharField(
        max_length=255,
        blank=True,
        help_text="e.g. part-time with another department lead",
    )
    is_active = models.BooleanField(default=True)
    """Один активный глава проекта (отдельно от роли в БД и от project-scoped grants)."""
    is_lead = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_project_members",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("project", "user"),
                name="uniq_project_member",
            )
        ]
        ordering = ("-joined_at",)

    def __str__(self) -> str:
        return f"{self.project_id}:{self.user_id}:{self.role}"


class ProjectResourceRequest(models.Model):
    """Запрос дополнительных людей на проект (от руководителя проекта → админы компании)."""

    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = (
        (STATUS_OPEN, "Open"),
        (STATUS_CLOSED, "Closed"),
    )

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="resource_requests")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_project_resource_requests",
    )
    message = models.TextField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_project_resource_requests",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("project", "status")),
            models.Index(fields=("status", "-created_at")),
        ]

    def __str__(self) -> str:
        return f"prr-{self.pk}:project-{self.project_id}"


class ProjectDocument(models.Model):
    """Файлы и внешние ссылки, привязанные к проекту (не «личный кабинет»)."""

    class Source(models.TextChoices):
        UPLOAD = "upload", "Upload"
        EXTERNAL = "external", "External link"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="documents")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_project_documents",
    )
    title = models.CharField(max_length=500)
    document_type = models.CharField(max_length=16)
    source = models.CharField(max_length=16, choices=Source.choices)
    external_href = models.TextField(blank=True)
    file = models.FileField(upload_to=project_document_upload_to, blank=True, null=True)
    storage_provider = models.ForeignKey(
        "storage.StorageProvider",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="project_documents",
    )
    storage_object_key = models.TextField(blank=True, default="")
    upload_stored_bytes = models.PositiveBigIntegerField(default=0)
    owner_label = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self) -> str:
        return f"{self.project_id}:{self.title[:40]}"

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
        project = self.project
        return {
            "id": f"pdoc-{self.pk}",
            "title": self.title,
            "type": self.document_type,
            "updated_at": self.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "owner": self.owner_label,
            "href": self.resolve_href(request),
            "project_id": str(project.pk),
            "project_name": project.name,
        }
