from apps.identity.capabilities import capabilities_for_roles
from apps.identity.models import UserCapability, UserRole
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
        elif code in {"ceo", "executive"}:
            normalized.add("executive")
        else:
            normalized.add(code)
    if not normalized:
        normalized.add("employee")
    return normalized


def _explicit_capabilities_for_user(user) -> set[str]:
    if not user or not user.is_authenticated:
        return set()
    return set(
        UserCapability.objects.filter(user=user).values_list("capability", flat=True)
    )


def _capabilities_from_access_grants(user) -> set[str]:
    """Bridge: map active access grants to legacy capability codes.

    Imported lazily to keep this module import-safe during Django startup
    (apps.access depends on settings.AUTH_USER_MODEL).
    """
    if not user or not user.is_authenticated:
        return set()
    try:
        from apps.access.bridge import capabilities_from_access
    except Exception:
        return set()
    try:
        return capabilities_from_access(user)
    except Exception:
        return set()


def effective_capabilities(user) -> set[str]:
    """Return effective capabilities = role bundle ∪ explicit ∪ access grants."""
    if not user or not user.is_authenticated:
        return set()
    role_caps = capabilities_for_roles(_normalized_roles_for_user(user))
    return (
        role_caps
        | _explicit_capabilities_for_user(user)
        | _capabilities_from_access_grants(user)
    )


def user_has_capability(user, capability: str) -> bool:
    return capability in effective_capabilities(user)


def normalized_roles_for_user(user):
    """Публичный доступ к нормализованным кодам ролей (для скоупа в доменных API)."""
    return _normalized_roles_for_user(user)


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


class HasCapability(BasePermission):
    """DRF permission that checks for a required capability on the view.

    Expected on the view:
    - ``required_capability: str`` — single capability code, OR
    - ``required_capabilities: tuple[str, ...]`` — all required.

    The check uses ``effective_capabilities`` which resolves role bundles
    plus explicit ``UserCapability`` grants.
    """

    message = "You do not have the required capability for this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        required: tuple[str, ...] = tuple(
            getattr(view, "required_capabilities", ())
        ) or ((getattr(view, "required_capability", None),) if getattr(view, "required_capability", None) else ())

        if not required:
            return True

        caps = effective_capabilities(request.user)
        return all(code in caps for code in required)
