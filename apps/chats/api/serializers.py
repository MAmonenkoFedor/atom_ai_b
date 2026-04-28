from rest_framework import serializers

from django.contrib.auth import get_user_model

from apps.chats.models import Chat, ChatMember, Message

User = get_user_model()


class ChatSerializer(serializers.ModelSerializer):
    chat_scope = serializers.CharField(read_only=True)
    project_id = serializers.IntegerField(source="project.id", read_only=True)
    org_unit_id = serializers.IntegerField(source="org_unit.id", read_only=True)
    created_by_id = serializers.IntegerField(source="created_by.id", read_only=True)

    class Meta:
        model = Chat
        fields = (
            "id",
            "chat_type",
            "chat_scope",
            "project_id",
            "org_unit_id",
            "title",
            "status",
            "created_by_id",
            "created_at",
            "updated_at",
        )


class ChatCreateSerializer(serializers.ModelSerializer):
    chat_scope = serializers.ChoiceField(choices=[c[0] for c in Chat.SCOPE_CHOICES], required=False)

    def validate(self, attrs):
        scope = attrs.get("chat_scope") or Chat.SCOPE_PERSONAL
        project = attrs.get("project")
        org_unit = attrs.get("org_unit")
        if scope == Chat.SCOPE_PROJECT and not project:
            raise serializers.ValidationError({"project": "project is required for project scope chat."})
        if scope == Chat.SCOPE_DEPARTMENT and not org_unit:
            raise serializers.ValidationError({"org_unit": "org_unit is required for department scope chat."})
        if scope == Chat.SCOPE_PERSONAL:
            attrs["project"] = None
            attrs["org_unit"] = None
        elif scope == Chat.SCOPE_PROJECT:
            attrs["org_unit"] = None
        elif scope == Chat.SCOPE_DEPARTMENT:
            attrs["project"] = None
        attrs["chat_scope"] = scope
        attrs["chat_type"] = Chat.TYPE_PROJECT if scope == Chat.SCOPE_PROJECT else Chat.TYPE_GENERAL
        return attrs

    class Meta:
        model = Chat
        fields = ("project", "org_unit", "chat_type", "chat_scope", "title", "status")


class ChatUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chat
        fields = ("title", "status")


class MessageSerializer(serializers.ModelSerializer):
    chat_id = serializers.IntegerField(source="chat.id", read_only=True)
    user_id = serializers.IntegerField(source="user.id", allow_null=True, read_only=True)
    username = serializers.CharField(source="user.username", allow_null=True, read_only=True)

    class Meta:
        model = Message
        fields = (
            "id",
            "chat_id",
            "user_id",
            "username",
            "message_type",
            "content",
            "metadata",
            "created_at",
        )


class MessageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ("message_type", "content", "metadata")


class ChatMemberSerializer(serializers.ModelSerializer):
    chat_id = serializers.IntegerField(source="chat.id", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = ChatMember
        fields = ("chat_id", "user_id", "username", "role", "joined_at")


class ChatMemberCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(min_value=1)
    role = serializers.ChoiceField(
        choices=[ChatMember.ROLE_OWNER, ChatMember.ROLE_MEMBER],
        required=False,
        default=ChatMember.ROLE_MEMBER,
    )

    def validate_user_id(self, value):
        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError("User not found.")
        return value


class ChatMemberUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=[ChatMember.ROLE_OWNER, ChatMember.ROLE_MEMBER])


class ChatShareCandidateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    full_name = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)
    job_title = serializers.CharField(allow_blank=True)
