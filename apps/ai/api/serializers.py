from django.conf import settings
from rest_framework import serializers

from apps.ai.models import (
    AiRun,
    PersonalAIDocument,
    PersonalAIPreference,
    PersonalNote,
    PersonalPromptTemplate,
)
from apps.llm_gateway.models import LlmRequestLog


def _allowed_model_ids() -> set[str]:
    allowed = {
        str(entry.get("id"))
        for entry in (getattr(settings, "AI_CHAT_ALLOWED_MODELS", []) or [])
        if entry.get("id")
    }
    image_client_id = str(getattr(settings, "HIGGSFIELD_CLIENT_MODEL_ID", "nano") or "").strip()
    if image_client_id:
        allowed.add(image_client_id)
    return allowed


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


class AiChatCompletionsRequestSerializer(serializers.Serializer):
    CONTEXT_CHOICES = ("project", "department", "task", "document", "workspace")

    thread_id = serializers.IntegerField(min_value=1)
    message = serializers.CharField(allow_blank=False, trim_whitespace=True)
    model = serializers.CharField(required=False, allow_blank=False)
    context_type = serializers.ChoiceField(choices=CONTEXT_CHOICES, required=False)
    context_id = serializers.CharField(required=False, allow_blank=False)
    aspect_ratio = serializers.CharField(required=False, allow_blank=False)
    resolution = serializers.CharField(required=False, allow_blank=False)

    def validate_model(self, value: str) -> str:
        allowed = _allowed_model_ids()
        if allowed and value not in allowed:
            raise serializers.ValidationError(
                "Model is not in the allowed list. Ask super-admin to enable it."
            )
        return value

    def validate(self, attrs):
        context_type = attrs.get("context_type")
        context_id = attrs.get("context_id")
        if context_id and not context_type:
            raise serializers.ValidationError(
                {"context_type": "context_type is required when context_id is provided."}
            )
        return attrs


class AiChatAllowedModelSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    provider = serializers.CharField(required=False, default="")
    specialty = serializers.CharField(required=False, default="")
    description = serializers.CharField(required=False, default="")
    is_default = serializers.BooleanField(required=False, default=False)
    context_tokens = serializers.IntegerField(required=False, default=0)


class PersonalAIPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonalAIPreference
        fields = (
            "personal_ai_enabled",
            "allowed_models",
            "monthly_limit",
            "can_upload_personal_docs",
            "updated_at",
        )
        read_only_fields = ("updated_at",)


class PersonalAIDocumentSerializer(serializers.ModelSerializer):
    href = serializers.SerializerMethodField()

    class Meta:
        model = PersonalAIDocument
        fields = (
            "id",
            "title",
            "document_type",
            "href",
            "external_href",
            "created_at",
            "updated_at",
        )

    def get_href(self, obj: PersonalAIDocument) -> str:
        request = self.context.get("request")
        if obj.file and request is not None:
            return request.build_absolute_uri(obj.file.url)
        return (obj.external_href or "").strip()


class PersonalAIDocumentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonalAIDocument
        fields = ("title", "document_type", "external_href", "file")


class PersonalAIDocumentShareToProjectSerializer(serializers.Serializer):
    project_id = serializers.IntegerField(min_value=1)


class PersonalPromptTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonalPromptTemplate
        fields = ("id", "title", "content", "tags", "is_favorite", "created_at", "updated_at")


class PersonalPromptTemplateCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonalPromptTemplate
        fields = ("title", "content", "tags", "is_favorite")


class PersonalNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonalNote
        fields = ("id", "title", "content", "created_at", "updated_at")


class PersonalNoteCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonalNote
        fields = ("title", "content")
