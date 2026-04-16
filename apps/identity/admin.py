from django.contrib import admin

from .models import Role, UserRole


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "name", "created_at")
    search_fields = ("code", "name")


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "role", "organization", "assigned_at")
    list_filter = ("role", "organization")
    search_fields = ("user__username", "user__email", "role__code")
