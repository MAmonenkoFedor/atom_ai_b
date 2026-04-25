from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    actor_role = models.CharField(max_length=64, blank=True)
    company_id = models.CharField(max_length=64, blank=True)
    department_id = models.CharField(max_length=64, blank=True)
    event_type = models.CharField(max_length=128)
    entity_type = models.CharField(max_length=64)
    entity_id = models.CharField(max_length=128, blank=True)
    action = models.CharField(max_length=64)
    project_id = models.CharField(max_length=64, blank=True)
    task_id = models.CharField(max_length=64, blank=True)
    chat_id = models.CharField(max_length=64, blank=True)
    request_path = models.CharField(max_length=512, blank=True)
    request_method = models.CharField(max_length=16, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    trace_id = models.CharField(max_length=64, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("created_at",)),
            models.Index(fields=("actor", "created_at")),
            models.Index(fields=("event_type", "created_at")),
            models.Index(fields=("project_id", "created_at")),
            models.Index(fields=("task_id", "created_at")),
            models.Index(fields=("chat_id", "created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.event_type}:{self.entity_type}:{self.entity_id}"
