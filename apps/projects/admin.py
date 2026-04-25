from django.contrib import admin

from .models import Project, ProjectDocument, ProjectMember


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "organization", "status", "created_by", "created_at")
    list_filter = ("organization", "status")
    search_fields = ("name", "description")


@admin.register(ProjectMember)
class ProjectMemberAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "user", "role", "is_active", "joined_at")
    list_filter = ("role", "is_active")
    search_fields = ("project__name", "user__username", "user__email")


@admin.register(ProjectDocument)
class ProjectDocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "project", "uploaded_by", "source", "document_type", "updated_at")
    list_filter = ("source", "document_type")
    search_fields = ("title", "project__name")
