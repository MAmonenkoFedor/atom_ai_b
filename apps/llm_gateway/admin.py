from django.contrib import admin

from .models import LlmModel, LlmModelProfile, LlmProvider, LlmRequestLog


@admin.register(LlmProvider)
class LlmProviderAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "name", "is_active", "priority", "created_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(LlmModel)
class LlmModelAdmin(admin.ModelAdmin):
    list_display = ("id", "provider", "code", "is_active", "context_window", "created_at")
    list_filter = ("provider", "is_active")
    search_fields = ("code", "display_name")


@admin.register(LlmModelProfile)
class LlmModelProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "is_active", "primary_model", "fallback_model")
    list_filter = ("is_active",)
    search_fields = ("code", "description")


@admin.register(LlmRequestLog)
class LlmRequestLogAdmin(admin.ModelAdmin):
    list_display = ("id", "ai_run", "status", "provider", "model", "latency_ms", "created_at")
    list_filter = ("status", "provider")
    search_fields = ("error_message", "response_excerpt")
