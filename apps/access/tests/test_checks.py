from django.test import TestCase

from apps.access.checks import check_ai_workspace_privacy_invariants
from apps.access.models import PermissionDefinition, RoleTemplate, RoleTemplatePermission


class AccessPrivacyChecksTests(TestCase):
    def test_fails_when_required_permissions_missing(self):
        result = check_ai_workspace_privacy_invariants()
        self.assertFalse(result.ok)
        self.assertTrue(any("ai.workspace.view_metadata" in err for err in result.errors))
        self.assertTrue(any("ai.workspace.view_content" in err for err in result.errors))

    def test_passes_for_expected_defaults(self):
        PermissionDefinition.objects.create(
            code="ai.workspace.view_metadata",
            name="Metadata",
            module=PermissionDefinition.MODULE_AI,
            allowed_scopes=["company", "ai_workspace"],
        )
        PermissionDefinition.objects.create(
            code="ai.workspace.view_content",
            name="Content",
            module=PermissionDefinition.MODULE_AI,
            allowed_scopes=["company", "ai_workspace"],
            is_sensitive=True,
        )
        template = RoleTemplate.objects.create(
            code="company_admin_base",
            name="Company Admin",
            default_scope_type="company",
            is_system=True,
        )
        RoleTemplatePermission.objects.create(
            role_template=template,
            permission_code="ai.workspace.view_metadata",
            grant_mode=RoleTemplatePermission.GRANT_MODE_USE_AND_DELEGATE,
            default_enabled=True,
        )

        result = check_ai_workspace_privacy_invariants()
        self.assertTrue(result.ok)
        self.assertEqual(result.errors, ())

    def test_fails_when_content_is_enabled_by_default_for_company_admin(self):
        PermissionDefinition.objects.create(
            code="ai.workspace.view_metadata",
            name="Metadata",
            module=PermissionDefinition.MODULE_AI,
            allowed_scopes=["company", "ai_workspace"],
        )
        PermissionDefinition.objects.create(
            code="ai.workspace.view_content",
            name="Content",
            module=PermissionDefinition.MODULE_AI,
            allowed_scopes=["company", "ai_workspace"],
            is_sensitive=True,
        )
        template = RoleTemplate.objects.create(
            code="company_admin_base",
            name="Company Admin",
            default_scope_type="company",
            is_system=True,
        )
        RoleTemplatePermission.objects.create(
            role_template=template,
            permission_code="ai.workspace.view_metadata",
            grant_mode=RoleTemplatePermission.GRANT_MODE_USE_AND_DELEGATE,
            default_enabled=True,
        )
        RoleTemplatePermission.objects.create(
            role_template=template,
            permission_code="ai.workspace.view_content",
            grant_mode=RoleTemplatePermission.GRANT_MODE_USE_AND_DELEGATE,
            default_enabled=True,
        )

        result = check_ai_workspace_privacy_invariants()
        self.assertFalse(result.ok)
        self.assertTrue(any("must not include ai.workspace.view_content" in err for err in result.errors))
