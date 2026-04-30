from django.test import TestCase

from apps.access.seed import CORE_PERMISSIONS, CORE_ROLE_TEMPLATES


class AccessSeedPrivacyDefaultsTests(TestCase):
    def test_ai_workspace_permissions_exist_in_catalog(self):
        codes = {item["code"] for item in CORE_PERMISSIONS}
        self.assertIn("ai.workspace.view_metadata", codes)
        self.assertIn("ai.workspace.view_content", codes)

    def test_company_admin_template_is_metadata_only_by_default(self):
        company_admin = next((t for t in CORE_ROLE_TEMPLATES if t["code"] == "company_admin_base"), None)
        self.assertIsNotNone(company_admin)
        permission_codes = {code for code, _mode in company_admin["permissions"]}
        self.assertIn("ai.workspace.view_metadata", permission_codes)
        self.assertNotIn("ai.workspace.view_content", permission_codes)
