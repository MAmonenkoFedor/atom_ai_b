"""resolve_access for scope_type=employee."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.access.policies import resolve_access
from apps.organizations.models import Organization, OrganizationMember

User = get_user_model()


class ResolveEmployeeAccessTests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create_user(
            username="emp_viewer",
            email="emp_viewer@example.com",
            password="pass12345",
        )
        self.target = User.objects.create_user(
            username="emp_target",
            email="emp_target@example.com",
            password="pass12345",
        )
        self.org = Organization.objects.create(name="EmpOrg", slug="emp-org")
        OrganizationMember.objects.create(user=self.viewer, organization=self.org, is_active=True)
        OrganizationMember.objects.create(user=self.target, organization=self.org, is_active=True)

    def test_employee_read_allowed_for_self(self):
        d = resolve_access(
            user=self.viewer,
            action="employee.read",
            scope_type="employee",
            scope_id=str(self.viewer.pk),
            resource=self.viewer,
        )
        self.assertTrue(d.allowed)
        self.assertEqual(d.access_level, "read")
        self.assertEqual(d.reason, "self")

    def test_employee_invalid_scope(self):
        d = resolve_access(
            user=self.viewer,
            action="employee.read",
            scope_type="employee",
            scope_id="999999",
            resource=None,
        )
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, "invalid_employee")

    @patch("apps.orgstructure.employee_permissions.has_employee_scoped_permission")
    def test_workspace_metadata_allowed_by_explicit_workspace_permission(self, has_scoped_permission):
        def _side_effect(user, employee, permission_code):
            return permission_code == "employee.view_workspace_metadata"

        has_scoped_permission.side_effect = _side_effect
        d = resolve_access(
            user=self.viewer,
            action="employee.view_workspace_metadata",
            scope_type="employee",
            scope_id=str(self.target.pk),
            resource=self.target,
        )
        self.assertTrue(d.allowed)
        self.assertEqual(d.access_level, "metadata")
        self.assertEqual(d.reason, "permission:employee.view_workspace_metadata")

    @patch("apps.orgstructure.employee_permissions.has_employee_scoped_permission")
    def test_employee_manage_roles_requires_manage_level(self, has_scoped_permission):
        def _side_effect(user, employee, permission_code):
            return permission_code == "employee.manage_roles"

        has_scoped_permission.side_effect = _side_effect
        d = resolve_access(
            user=self.viewer,
            action="employee.manage_roles",
            scope_type="employee",
            scope_id=str(self.target.pk),
            resource=self.target,
        )
        self.assertTrue(d.allowed)
        self.assertEqual(d.access_level, "manage")
        self.assertEqual(d.reason, "permission:employee.manage_roles")

    @patch("apps.orgstructure.employee_permissions.has_employee_scoped_permission")
    def test_employee_workspace_content_denied_without_content_permission(self, has_scoped_permission):
        has_scoped_permission.return_value = False
        d = resolve_access(
            user=self.viewer,
            action="employee.view_workspace_content",
            scope_type="employee",
            scope_id=str(self.target.pk),
            resource=self.target,
        )
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, "requires:employee.view_workspace_content")
