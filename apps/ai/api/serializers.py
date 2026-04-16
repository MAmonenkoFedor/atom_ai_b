from rest_framework import serializers

from apps.ai.models import AiRun
from apps.llm_gateway.models import LlmRequestLog


class AiRunSerializer(serializers.ModelSerializer):
    run_id = serializers.IntegerField(source="id", read_only=True)
    project_id = serializers.IntegerField(source="project.id", read_only=True)
    chat_id = serializers.IntegerField(source="chat.id", read_only=True)
    message_id = serializers.IntegerField(source="message.id", allow_null=True, read_only=True)

    class Meta:
        model = AiRun
        fields = (
            "run_id",
            "status",
            "project_id",
            "chat_id",
            "message_id",
            "provider",
            "model",
            "citations",
            "usage",
            "output_text",
            "error_message",
            "created_at",
            "started_at",
            "completed_at",
        )


class AiRunCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AiRun
        fields = ("project", "chat", "message", "provider", "model")


class AiRunExecuteSerializer(serializers.Serializer):
    profile = serializers.CharField(required=False, allow_blank=False, default="chat_balanced")
    prompt = serializers.CharField(required=False, allow_blank=False)


class AiRunLogSerializer(serializers.ModelSerializer):
    provider = serializers.CharField(source="provider.code", allow_null=True, read_only=True)
    model = serializers.CharField(source="model.code", allow_null=True, read_only=True)
    profile = serializers.CharField(source="profile.code", allow_null=True, read_only=True)

    class Meta:
        model = LlmRequestLog
        fields = (
            "id",
            "status",
            "provider",
            "model",
            "profile",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "latency_ms",
            "error_message",
            "response_excerpt",
            "created_at",
        )
