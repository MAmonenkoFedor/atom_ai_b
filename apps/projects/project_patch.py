"""PATCH /projects/<pk> field groups and settings key allowlist (P1.1)."""

from __future__ import annotations

# Ordinary working fields → resolve_access action ``project.update``.
PATCH_UPDATE_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "description",
        "status",
        "code",
        "public_summary",
        "planned_start",
        "planned_end",
    }
)

# Project settings / governance → ``project.manage_settings`` (min access manage/admin in policies).
PATCH_SETTINGS_FIELDS: frozenset[str] = frozenset(
    {
        "primary_org_unit",
        "project_settings",
    }
)

# Reserved for owner / org / billing (separate permissions later). Not exposed on PATCH yet.
PATCH_DANGEROUS_FIELDS: frozenset[str] = frozenset()

# Shallow-merge keys inside ``Project.project_settings`` JSON (validated on write).
ALLOWED_PROJECT_SETTINGS_KEYS: frozenset[str] = frozenset(
    {
        "visibility",
        "workflow",
        "default_document_policy",
        "ai_defaults",
        "integrations",
        "external_sharing",
    }
)


def classify_project_patch_keys(touched: set[str]) -> tuple[set[str], set[str], set[str]]:
    """Return (update_keys, settings_keys, dangerous_keys) from serializer validated_data keys."""

    return (
        set(touched) & PATCH_UPDATE_FIELDS,
        set(touched) & PATCH_SETTINGS_FIELDS,
        set(touched) & PATCH_DANGEROUS_FIELDS,
    )


def sensitive_patch_keys(touched: set[str]) -> set[str]:
    return (set(touched) & PATCH_SETTINGS_FIELDS) | (set(touched) & PATCH_DANGEROUS_FIELDS)
