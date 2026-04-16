from django.contrib import admin

from .models import AiRun


@admin.register(AiRun)
class AiRunAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "chat", "status", "provider", "model", "created_at")
    list_filter = ("status", "provider", "model")
    search_fields = ("output_text", "error_message")
