"""Canonical capability catalog for the platform.

Capabilities are fine-grained permission flags that can be:
- bundled under a role (implicit through role code), or
- granted explicitly per-user via ``UserCapability``.

The super-admin cabinet resolves effective capabilities as
``role_bundle(role_codes) | explicit_user_capabilities``.

Keep this module import-safe: no Django model imports here.
"""

from __future__ import annotations

USERS_VIEW_ALL = "users.view_all"
USERS_INVITE = "users.invite"
USERS_DISABLE = "users.disable"
USERS_ENABLE = "users.enable"
USERS_FORCE_LOGOUT = "users.force_logout"

ROLES_MANAGE = "roles.manage"
CAPABILITIES_MANAGE = "capabilities.manage"

AUDIT_VIEW_ALL = "audit.view_all"
AUDIT_EXPORT = "audit.export"
AUDIT_VIEW_SENSITIVE = "audit.view_sensitive"

CHATS_VIEW_ALL = "chats.view_all"
CHATS_VIEW_TRANSCRIPTS = "chats.view_transcripts"
CHATS_MODERATE = "chats.moderate"
CHATS_DELETE = "chats.delete"
CHATS_EXPORT = "chats.export"

LLM_PROVIDERS_MANAGE = "llm.providers.manage"
LLM_MODELS_MANAGE = "llm.models.manage"
LLM_POLICIES_MANAGE = "llm.policies.manage"
LLM_BUDGETS_MANAGE = "llm.budgets.manage"
LLM_USAGE_VIEW_ALL = "llm.usage.view_all"

STORAGE_PROVIDERS_MANAGE = "storage.providers.manage"
STORAGE_QUOTAS_MANAGE = "storage.quotas.manage"
STORAGE_USAGE_VIEW_ALL = "storage.usage.view_all"

ALL_CAPABILITIES: tuple[str, ...] = (
    USERS_VIEW_ALL,
    USERS_INVITE,
    USERS_DISABLE,
    USERS_ENABLE,
    USERS_FORCE_LOGOUT,
    ROLES_MANAGE,
    CAPABILITIES_MANAGE,
    AUDIT_VIEW_ALL,
    AUDIT_EXPORT,
    AUDIT_VIEW_SENSITIVE,
    CHATS_VIEW_ALL,
    CHATS_VIEW_TRANSCRIPTS,
    CHATS_MODERATE,
    CHATS_DELETE,
    CHATS_EXPORT,
    LLM_PROVIDERS_MANAGE,
    LLM_MODELS_MANAGE,
    LLM_POLICIES_MANAGE,
    LLM_BUDGETS_MANAGE,
    LLM_USAGE_VIEW_ALL,
    STORAGE_PROVIDERS_MANAGE,
    STORAGE_QUOTAS_MANAGE,
    STORAGE_USAGE_VIEW_ALL,
)

_SUPER_ADMIN_BUNDLE: frozenset[str] = frozenset(ALL_CAPABILITIES)

_COMPANY_ADMIN_BUNDLE: frozenset[str] = frozenset(
    {
        USERS_VIEW_ALL,
        USERS_INVITE,
        USERS_DISABLE,
        USERS_ENABLE,
        ROLES_MANAGE,
        AUDIT_VIEW_ALL,
        CHATS_VIEW_ALL,
        LLM_USAGE_VIEW_ALL,
        STORAGE_USAGE_VIEW_ALL,
    }
)

_MANAGER_BUNDLE: frozenset[str] = frozenset({CHATS_VIEW_ALL})

_EMPLOYEE_BUNDLE: frozenset[str] = frozenset()

_AUDITOR_BUNDLE: frozenset[str] = frozenset(
    {
        AUDIT_VIEW_ALL,
        AUDIT_EXPORT,
        AUDIT_VIEW_SENSITIVE,
    }
)

ROLE_CAPABILITY_BUNDLE: dict[str, frozenset[str]] = {
    "super_admin": _SUPER_ADMIN_BUNDLE,
    "company_admin": _COMPANY_ADMIN_BUNDLE,
    "admin": _COMPANY_ADMIN_BUNDLE,
    "executive": _COMPANY_ADMIN_BUNDLE,
    "ceo": _COMPANY_ADMIN_BUNDLE,
    "manager": _MANAGER_BUNDLE,
    "employee": _EMPLOYEE_BUNDLE,
    "auditor": _AUDITOR_BUNDLE,
}


def capabilities_for_roles(role_codes: set[str] | frozenset[str]) -> set[str]:
    """Return union of capability bundles for provided role codes.

    Unknown role codes contribute no capabilities.
    """
    result: set[str] = set()
    for code in role_codes:
        result |= ROLE_CAPABILITY_BUNDLE.get(code, frozenset())
    return result


def is_known_capability(code: str) -> bool:
    return code in _SUPER_ADMIN_BUNDLE
