from rest_framework import serializers

from apps.chats.models import Chat, Message


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
