from django.contrib import admin

from .models import Chat, ChatMember, Message


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "project", "status", "created_by", "created_at")
    list_filter = ("status", "project")
    search_fields = ("title",)


@admin.register(ChatMember)
class ChatMemberAdmin(admin.ModelAdmin):
    list_display = ("id", "chat", "user", "role", "joined_at")
    list_filter = ("role",)
    search_fields = ("chat__title", "user__username", "user__email")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "chat", "user", "message_type", "created_at")
    list_filter = ("message_type",)
    search_fields = ("chat__title", "content")
