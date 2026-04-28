from django.conf import settings
from django.db import models


class AiRun(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CANCELED = "canceled"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELED, "Canceled"),
    )

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="ai_runs",
    )
    chat = models.ForeignKey(
        "chats.Chat",
        on_delete=models.CASCADE,
        related_name="ai_runs",
    )
    message = models.ForeignKey(
        "chats.Message",
        on_delete=models.SET_NULL,
        related_name="ai_runs",
        null=True,
        blank=True,
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="ai_runs",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING)
    provider = models.CharField(max_length=64, blank=True)
    model = models.CharField(max_length=128, blank=True)
    citations = models.JSONField(default=list, blank=True)
    usage = models.JSONField(default=dict, blank=True)
    output_text = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.id}:{self.status}"


class PersonalAIPreference(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="personal_ai_preference",
    )
    personal_ai_enabled = models.BooleanField(default=True)
    allowed_models = models.JSONField(default=list, blank=True)
    monthly_limit = models.PositiveIntegerField(default=100000)
    can_upload_personal_docs = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user_id",)

    def __str__(self) -> str:
        return f"personal-ai:{self.user_id}:{'on' if self.personal_ai_enabled else 'off'}"


class PersonalAIDocument(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="personal_ai_documents",
    )
    title = models.CharField(max_length=500)
    document_type = models.CharField(max_length=32, default="doc")
    file = models.FileField(upload_to="personal_ai_docs/", blank=True, null=True)
    external_href = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-id")

    def __str__(self) -> str:
        return f"personal-doc:{self.user_id}:{self.title[:32]}"


class PersonalPromptTemplate(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="personal_prompt_templates",
    )
    title = models.CharField(max_length=255)
    content = models.TextField()
    tags = models.JSONField(default=list, blank=True)
    is_favorite = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-is_favorite", "-updated_at", "-id")

    def __str__(self) -> str:
        return f"prompt:{self.user_id}:{self.title[:32]}"


class PersonalNote(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="personal_ai_notes",
    )
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-id")

    def __str__(self) -> str:
        return f"note:{self.user_id}:{self.title[:32]}"
