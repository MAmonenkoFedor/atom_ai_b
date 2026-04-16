from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.identity.models import Role, UserRole

User = get_user_model()


class ParallelContractPermissionsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.role_employee = Role.objects.create(code="employee", name="Employee")
        self.role_manager = Role.objects.create(code="manager", name="Manager")
        self.role_company_admin = Role.objects.create(code="company_admin", name="Company Admin")
        self.role_super_admin = Role.objects.create(code="super_admin", name="Super Admin")

        self.employee = User.objects.create_user(
            username="employee_u",
            email="employee@example.com",
            password="pass12345",
        )
        self.manager = User.objects.create_user(
            username="manager_u",
            email="manager@example.com",
            password="pass12345",
        )
        self.company_admin = User.objects.create_user(
            username="company_admin_u",
            email="company_admin@example.com",
            password="pass12345",
        )
        self.super_admin = User.objects.create_user(
            username="super_admin_u",
            email="super_admin@example.com",
            password="pass12345",
        )

        UserRole.objects.create(user=self.employee, role=self.role_employee)
        UserRole.objects.create(user=self.manager, role=self.role_manager)
        UserRole.objects.create(user=self.company_admin, role=self.role_company_admin)
        UserRole.objects.create(user=self.super_admin, role=self.role_super_admin)

    def test_employee_forbidden_for_company_admin_endpoint(self):
        self.client.force_authenticate(user=self.employee)
        response = self.client.get("/api/company/admin/overview")
        self.assertEqual(response.status_code, 403)

    def test_company_admin_allowed_for_company_admin_endpoint(self):
        self.client.force_authenticate(user=self.company_admin)
        response = self.client.get("/api/company/admin/overview")
        self.assertEqual(response.status_code, 200)

    def test_company_admin_forbidden_for_super_admin_endpoint(self):
        self.client.force_authenticate(user=self.company_admin)
        response = self.client.get("/api/admin/platform/overview")
        self.assertEqual(response.status_code, 403)

    def test_super_admin_allowed_for_super_admin_endpoint(self):
        self.client.force_authenticate(user=self.super_admin)
        response = self.client.get("/api/admin/platform/overview")
        self.assertEqual(response.status_code, 200)

    def test_super_admin_allowed_for_action_center_endpoint(self):
        self.client.force_authenticate(user=self.super_admin)
        response = self.client.get("/api/admin/actions/stats")
        self.assertEqual(response.status_code, 200)

    def test_manager_forbidden_for_action_center_endpoint(self):
        self.client.force_authenticate(user=self.manager)
        response = self.client.get("/api/admin/actions/stats")
        self.assertEqual(response.status_code, 403)
