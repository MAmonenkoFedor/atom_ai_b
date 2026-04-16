from django.contrib import admin

from .models import OrgUnit, OrgUnitMember, UserManagerLink


@admin.register(OrgUnit)
class OrgUnitAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "organization", "parent", "is_active", "created_at")
    list_filter = ("organization", "is_active")
    search_fields = ("name", "code")


@admin.register(OrgUnitMember)
class OrgUnitMemberAdmin(admin.ModelAdmin):
    list_display = ("id", "org_unit", "user", "position", "is_lead", "joined_at")
    list_filter = ("org_unit", "is_lead")
    search_fields = ("org_unit__name", "user__username", "user__email")


@admin.register(UserManagerLink)
class UserManagerLinkAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "employee", "manager", "created_at")
    list_filter = ("organization",)
    search_fields = ("employee__username", "manager__username")
