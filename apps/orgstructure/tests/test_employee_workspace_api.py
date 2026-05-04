"""HTTP tests for /api/v1/employees/* foundation endpoints."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.access.models import PermissionDefinition, PermissionGrant
from apps.identity.models import Role, UserRole
from apps.organizations.models import Organization, OrganizationMember
from apps.orgstructure.models import OrgUnit, OrgUnitMember
from apps.projects.models import Project, ProjectMember

User = get_user_model()


class EmployeeWorkspaceApiTests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create_user(
            username="ew_viewer",
            email="ew_viewer@example.com",
            password="pass12345",
        )
        self.target = User.objects.create_user(
            username="ew_target",
            email="ew_target@example.com",
            password="pass12345",
        )
        self.other = User.objects.create_user(
            username="ew_other",
            email="ew_other@example.com",
            password="pass12345",
        )
        self.org = Organization.objects.create(name="EW Org", slug="ew-org")
        OrganizationMember.objects.create(user=self.viewer, organization=self.org, is_active=True, job_title="Lead")
        OrganizationMember.objects.create(user=self.target, organization=self.org, is_active=True, job_title="IC")
        OrganizationMember.objects.create(user=self.other, organization=self.org, is_active=True, job_title="Ops")

        self.dept = OrgUnit.objects.create(organization=self.org, name="EW Dept", code="ew")
        OrgUnitMember.objects.create(org_unit=self.dept, user=self.viewer, position="Lead", is_lead=True)
        OrgUnitMember.objects.create(org_unit=self.dept, user=self.target, position="Engineer", is_lead=False)

        self.project = Project.objects.create(
            organization=self.org,
            primary_org_unit=self.dept,
            name="EW Project",
            created_by=self.viewer,
        )
        ProjectMember.objects.create(project=self.project, user=self.target, role=ProjectMember.ROLE_EDITOR)
        PermissionDefinition.objects.create(
            code="employee.view_metadata",
            name="Employee metadata",
            module=PermissionDefinition.MODULE_ORGANIZATION,
            allowed_scopes=["company", "department", "employee"],
        )
        PermissionDefinition.objects.create(
            code="employee.view_workspace_metadata",
            name="Employee workspace metadata",
            module=PermissionDefinition.MODULE_ORGANIZATION,
            allowed_scopes=["company", "department", "employee"],
        )
        PermissionDefinition.objects.create(
            code="employee.update",
            name="Employee update",
            module=PermissionDefinition.MODULE_ORGANIZATION,
            allowed_scopes=["company", "department", "employee"],
        )
        PermissionDefinition.objects.create(
            code="employee.manage_roles",
            name="Employee manage roles",
            module=PermissionDefinition.MODULE_ORGANIZATION,
            allowed_scopes=["company", "department", "employee"],
        )
        PermissionDefinition.objects.create(
            code="employee.read",
            name="Employee read",
            module=PermissionDefinition.MODULE_ORGANIZATION,
            allowed_scopes=["company", "department", "employee"],
        )
        self.role_manager = Role.objects.create(code="manager", name="Manager")
        UserRole.objects.create(user=self.target, role=self.role_manager, organization=self.org)

    def test_employees_list_contains_shared_department_users(self):
        client = APIClient()
        client.force_authenticate(user=self.viewer)
        r = client.get(reverse("employees-list-v1"))
        self.assertEqual(r.status_code, 200)
        ids = {row["id"] for row in r.data}
        self.assertIn(self.viewer.pk, ids)
        self.assertIn(self.target.pk, ids)
        self.assertNotIn(self.other.pk, ids)

    def test_employee_detail_masks_read_fields_for_metadata_only(self):
        PermissionGrant.objects.create(
            employee=self.viewer,
            permission_code="employee.view_metadata",
            scope_type="employee",
            scope_id=str(self.other.pk),
            grant_mode=PermissionGrant.GRANT_MODE_USE_ONLY,
        )
        client = APIClient()
        client.force_authenticate(user=self.viewer)
        r = client.get(reverse("employees-detail-v1", kwargs={"user_id": self.other.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["access_level"], "metadata")
        self.assertEqual(r.data["email"], "")

    def test_employee_departments_requires_read(self):
        PermissionGrant.objects.create(
            employee=self.viewer,
            permission_code="employee.view_metadata",
            scope_type="employee",
            scope_id=str(self.other.pk),
            grant_mode=PermissionGrant.GRANT_MODE_USE_ONLY,
        )
        client = APIClient()
        client.force_authenticate(user=self.viewer)
        r = client.get(reverse("employees-departments-v1", kwargs={"user_id": self.other.pk}))
        self.assertEqual(r.status_code, 403)

    def test_employee_projects_returns_rows_with_read_access(self):
        client = APIClient()
        client.force_authenticate(user=self.viewer)
        r = client.get(reverse("employees-projects-v1", kwargs={"user_id": self.target.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]["project_id"], self.project.pk)

    @patch("apps.orgstructure.api.employee_workspace_views.emit_audit_event")
    def test_workspace_metadata_access_emits_metadata_event(self, emit_audit):
        PermissionGrant.objects.create(
            employee=self.viewer,
            permission_code="employee.view_workspace_metadata",
            scope_type="employee",
            scope_id=str(self.other.pk),
            grant_mode=PermissionGrant.GRANT_MODE_USE_ONLY,
        )
        client = APIClient()
        client.force_authenticate(user=self.viewer)
        r = client.get(reverse("employees-workspace-v1", kwargs={"user_id": self.other.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["access_level"], "metadata")
        event_types = [c.kwargs.get("event_type") for c in emit_audit.call_args_list]
        self.assertIn("employee.workspace_metadata_accessed", event_types)

    def test_employee_patch_forbidden_without_employee_update(self):
        client = APIClient()
        client.force_authenticate(user=self.viewer)
        r = client.patch(
            reverse("employees-detail-v1", kwargs={"user_id": self.target.pk}),
            {"first_name": "Neo"},
            format="json",
        )
        self.assertEqual(r.status_code, 403)

    def test_employee_patch_ok_with_employee_update_grant(self):
        PermissionGrant.objects.create(
            employee=self.viewer,
            permission_code="employee.update",
            scope_type="employee",
            scope_id=str(self.target.pk),
            grant_mode=PermissionGrant.GRANT_MODE_USE_ONLY,
        )
        client = APIClient()
        client.force_authenticate(user=self.viewer)
        r = client.patch(
            reverse("employees-detail-v1", kwargs={"user_id": self.target.pk}),
            {"first_name": "Neo", "job_title": "Architect"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.target.refresh_from_db()
        self.assertEqual(self.target.first_name, "Neo")

    def test_roles_update_requires_manage_roles(self):
        client = APIClient()
        client.force_authenticate(user=self.viewer)
        r = client.put(
            reverse("employees-roles-v1", kwargs={"user_id": self.target.pk}),
            {"system_role": "manager"},
            format="json",
        )
        self.assertEqual(r.status_code, 403)

    def test_roles_update_ok_with_manage_roles(self):
        PermissionGrant.objects.create(
            employee=self.viewer,
            permission_code="employee.manage_roles",
            scope_type="employee",
            scope_id=str(self.target.pk),
            grant_mode=PermissionGrant.GRANT_MODE_USE_ONLY,
        )
        role_admin = Role.objects.create(code="admin", name="Admin")
        client = APIClient()
        client.force_authenticate(user=self.viewer)
        r = client.put(
            reverse("employees-roles-v1", kwargs={"user_id": self.target.pk}),
            {"system_role": role_admin.code},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        assignment = UserRole.objects.select_related("role").get(user=self.target)
        self.assertEqual(assignment.role.code, role_admin.code)

    def test_permissions_grant_and_revoke_flow(self):
        PermissionGrant.objects.create(
            employee=self.viewer,
            permission_code="employee.manage_roles",
            scope_type="employee",
            scope_id=str(self.target.pk),
            grant_mode=PermissionGrant.GRANT_MODE_USE_ONLY,
        )
        client = APIClient()
        client.force_authenticate(user=self.viewer)
        create = client.post(
            reverse("employees-permissions-v1", kwargs={"user_id": self.target.pk}),
            {"permission_code": "employee.view_metadata", "scope_type": "employee"},
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        grant_id = int(create.data["id"])

        revoke = client.post(
            reverse(
                "employees-permissions-revoke-v1",
                kwargs={"user_id": self.target.pk, "grant_id": grant_id},
            ),
            {"note": "cleanup"},
            format="json",
        )
        self.assertEqual(revoke.status_code, 200)
        self.assertEqual(revoke.data["status"], PermissionGrant.STATUS_REVOKED)
