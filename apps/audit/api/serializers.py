from rest_framework import serializers

from apps.audit.models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    actor_id = serializers.IntegerField(source="actor.id", read_only=True, allow_null=True)
    actor_username = serializers.CharField(source="actor.username", read_only=True, allow_blank=True)

    class Meta:
        model = AuditEvent
        fields = (
            "id",
            "created_at",
            "event_type",
            "entity_type",
            "entity_id",
            "action",
            "actor_id",
            "actor_username",
            "actor_role",
            "company_id",
            "department_id",
            "project_id",
            "task_id",
            "chat_id",
            "request_path",
            "request_method",
            "ip_address",
            "user_agent",
            "trace_id",
            "payload",
        )
