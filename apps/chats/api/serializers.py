from rest_framework import serializers

from django.contrib.auth import get_user_model

from apps.chats.models import Chat, ChatMember, Message

User = get_user_model()


class ChatSerializer(serializers.ModelSerializer):
    project_id = serializers.IntegerField(source="project.id", read_only=True)
    created_by_id = serializers.IntegerField(source="created_by.id", read_only=True)

    class Meta:
        model = Chat
        fields = (
            "id",
            "project_id",
            "title",
            "status",
            "created_by_id",
            "created_at",
            "updated_at",
        )


class ChatCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chat
        fields = ("project", "title", "status")


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
