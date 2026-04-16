from apps.identity.models import UserRole
from rest_framework.permissions import BasePermission


def _normalized_roles_for_user(user):
    if not user or not user.is_authenticated:
        return set()

    roles = set(
        UserRole.objects.filter(user=user)
        .select_related("role")
        .values_list("role__code", flat=True)
    )
    normalized = set()
    for code in roles:
        if code == "admin":
            normalized.add("company_admin")
        else:
            normalized.add(code)
    if not normalized:
        normalized.add("employee")
    return normalized


class IsCompanyAdminOrSuperAdmin(BasePermission):
    message = "You do not have permission to access company admin endpoints."

    def has_permission(self, request, view):
        roles = _normalized_roles_for_user(request.user)
        return "company_admin" in roles or "super_admin" in roles


class IsSuperAdmin(BasePermission):
    message = "You do not have permission to access super admin endpoints."

    def has_permission(self, request, view):
        roles = _normalized_roles_for_user(request.user)
        return "super_admin" in roles
