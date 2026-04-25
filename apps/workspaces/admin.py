from django.contrib import admin

from apps.workspaces.models import WorkspaceCabinetDocument


@admin.register(WorkspaceCabinetDocument)
class WorkspaceCabinetDocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user", "source", "document_type", "updated_at")
    list_filter = ("source", "document_type")
    search_fields = ("title", "user__username", "external_href")
    readonly_fields = ("created_at", "updated_at")
