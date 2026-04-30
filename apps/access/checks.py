"""Runtime invariants for access-control privacy defaults."""

from __future__ import annotations

from dataclasses import dataclass

from apps.access.models import PermissionDefinition, RoleTemplate, RoleTemplatePermission


@dataclass(frozen=True)
class PrivacyInvariantResult:
    ok: bool
    errors: tuple[str, ...]


def check_ai_workspace_privacy_invariants() -> PrivacyInvariantResult:
    errors: list[str] = []

    required_permission_codes = (
        "ai.workspace.view_metadata",
        "ai.workspace.view_content",
    )
    existing_codes = set(
        PermissionDefinition.objects.filter(code__in=required_permission_codes).values_list(
            "code",
            flat=True,
        )
    )
    for code in required_permission_codes:
        if code not in existing_codes:
            errors.append(f"Missing PermissionDefinition: {code}")

    template = RoleTemplate.objects.filter(code="company_admin_base").first()
    if template is None:
        errors.append("Missing RoleTemplate: company_admin_base")
        return PrivacyInvariantResult(ok=False, errors=tuple(errors))

    template_codes = set(
        RoleTemplatePermission.objects.filter(
            role_template=template,
            default_enabled=True,
        ).values_list("permission_code", flat=True)
    )

    if "ai.workspace.view_metadata" not in template_codes:
        errors.append("company_admin_base must include ai.workspace.view_metadata")

    if "ai.workspace.view_content" in template_codes:
        errors.append("company_admin_base must not include ai.workspace.view_content by default")

    return PrivacyInvariantResult(ok=not errors, errors=tuple(errors))
