"""HTTP tests for /api/v1/departments/*."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Organization, OrganizationMember
from apps.orgstructure.models import OrgUnit, OrgUnitDocument, OrgUnitMember

User = get_user_model()


class DepartmentWorkspaceApiTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            username="dw_member",
            email="dw_member@example.com",
            password="pass12345",
        )
        self.stranger = User.objects.create_user(
            username="dw_out",
            email="dw_out@example.com",
            password="pass12345",
        )
        self.org = Organization.objects.create(name="DW Org", slug="dw-org")
        OrganizationMember.objects.create(user=self.member, organization=self.org, is_active=True)
        OrganizationMember.objects.create(user=self.stranger, organization=self.org, is_active=True)
        self.ou = OrgUnit.objects.create(organization=self.org, name="DW Dept", code="dw")
        OrgUnitMember.objects.create(org_unit=self.ou, user=self.member, is_lead=False, position="IC")
        self.lead = User.objects.create_user(
            username="dw_lead",
            email="dw_lead@example.com",
            password="pass12345",
        )
        OrganizationMember.objects.create(user=self.lead, organization=self.org, is_active=True)
        OrgUnitMember.objects.create(org_unit=self.ou, user=self.lead, is_lead=True, position="Lead")
        self.extra = User.objects.create_user(
            username="dw_extra",
            email="dw_extra@example.com",
            password="pass12345",
        )
        OrganizationMember.objects.create(user=self.extra, organization=self.org, is_active=True)

    def test_list_visible_for_member(self):
        url = reverse("departments-list")
        client = APIClient()
        client.force_authenticate(user=self.member)
        r = client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(len(r.data), 1)
        ids = [row["id"] for row in r.data]
        self.assertIn(self.ou.pk, ids)

    def test_detail_for_member(self):
        url = reverse("departments-detail", kwargs={"pk": self.ou.pk})
        client = APIClient()
        client.force_authenticate(user=self.member)
        r = client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data.get("id"), self.ou.pk)
        self.assertIn("access_level", r.data)

    def test_stranger_no_department_access_returns_404_detail(self):
        url = reverse("departments-detail", kwargs={"pk": self.ou.pk})
        client = APIClient()
        client.force_authenticate(user=self.stranger)
        r = client.get(url)
        self.assertEqual(r.status_code, 404)

    def test_employees_requires_member(self):
        url = reverse("departments-employees", kwargs={"pk": self.ou.pk})
        client = APIClient()
        client.force_authenticate(user=self.stranger)
        r = client.get(url)
        self.assertEqual(r.status_code, 404)

    def test_employees_list_ok_for_department_member(self):
        url = reverse("departments-employees", kwargs={"pk": self.ou.pk})
        client = APIClient()
        client.force_authenticate(user=self.member)
        r = client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 2)
        user_ids = {row["user_id"] for row in r.data}
        self.assertEqual(user_ids, {self.member.pk, self.lead.pk})

    def test_workspace_includes_documents_link_when_department_read(self):
        url = reverse("departments-workspace", kwargs={"pk": self.ou.pk})
        client = APIClient()
        client.force_authenticate(user=self.member)
        r = client.get(url)
        self.assertEqual(r.status_code, 200)
        ws = r.data.get("workspace") or {}
        links = ws.get("links") or {}
        self.assertIn("documents", links)
        self.assertIn(f"/api/v1/departments/{self.ou.pk}/documents", links["documents"])

    @patch("apps.orgstructure.api.department_workspace_views.emit_audit_event")
    def test_documents_list_empty_emits_metadata_audit(self, emit_audit):
        url = reverse("departments-documents-list", kwargs={"pk": self.ou.pk})
        client = APIClient()
        client.force_authenticate(user=self.member)
        r = client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, [])
        event_types = [c.kwargs.get("event_type") for c in emit_audit.call_args_list]
        self.assertIn("department.document_metadata_accessed", event_types)

    @patch("apps.orgstructure.api.department_workspace_views.emit_audit_event")
    def test_documents_list_with_link_emits_content_audit(self, emit_audit):
        OrgUnitDocument.objects.create(
            org_unit=self.ou,
            uploaded_by=self.member,
            title="Ext",
            document_type="link",
            source=OrgUnitDocument.Source.EXTERNAL,
            external_href="https://example.com/doc",
            owner_label="M",
        )
        url = reverse("departments-documents-list", kwargs={"pk": self.ou.pk})
        client = APIClient()
        client.force_authenticate(user=self.member)
        r = client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 1)
        self.assertTrue((r.data[0].get("href") or "").strip())
        event_types = [c.kwargs.get("event_type") for c in emit_audit.call_args_list]
        self.assertIn("department.document_content_accessed", event_types)

    def test_documents_list_stranger_404(self):
        url = reverse("departments-documents-list", kwargs={"pk": self.ou.pk})
        client = APIClient()
        client.force_authenticate(user=self.stranger)
        r = client.get(url)
        self.assertEqual(r.status_code, 404)

    def test_member_patch_department_forbidden(self):
        url = reverse("departments-detail", kwargs={"pk": self.ou.pk})
        client = APIClient()
        client.force_authenticate(user=self.member)
        r = client.patch(url, {"name": "Renamed"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_stranger_patch_department_404(self):
        url = reverse("departments-detail", kwargs={"pk": self.ou.pk})
        client = APIClient()
        client.force_authenticate(user=self.stranger)
        r = client.patch(url, {"name": "X"}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_lead_patch_department_ok(self):
        url = reverse("departments-detail", kwargs={"pk": self.ou.pk})
        client = APIClient()
        client.force_authenticate(user=self.lead)
        r = client.patch(url, {"name": "DW Dept Renamed", "description": "Hello"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data.get("name"), "DW Dept Renamed")
        self.assertEqual(r.data.get("description"), "Hello")
        self.ou.refresh_from_db()
        self.assertEqual(self.ou.name, "DW Dept Renamed")

    def test_member_post_employee_forbidden(self):
        url = reverse("departments-employees", kwargs={"pk": self.ou.pk})
        client = APIClient()
        client.force_authenticate(user=self.member)
        r = client.post(url, {"user_id": self.extra.pk, "position": "Dev"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_lead_post_employee_ok(self):
        url = reverse("departments-employees", kwargs={"pk": self.ou.pk})
        client = APIClient()
        client.force_authenticate(user=self.lead)
        r = client.post(url, {"user_id": self.extra.pk, "position": "Dev"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data.get("user_id"), self.extra.pk)
        self.assertTrue(
            OrgUnitMember.objects.filter(org_unit=self.ou, user_id=self.extra.pk).exists()
        )

    def test_lead_delete_member_ok(self):
        url = reverse(
            "departments-employees-detail",
            kwargs={"pk": self.ou.pk, "employee_id": self.member.pk},
        )
        client = APIClient()
        client.force_authenticate(user=self.lead)
        r = client.delete(url)
        self.assertEqual(r.status_code, 204)
        self.assertFalse(
            OrgUnitMember.objects.filter(org_unit=self.ou, user_id=self.member.pk).exists()
        )

    def test_lead_delete_non_member_404(self):
        url = reverse(
            "departments-employees-detail",
            kwargs={"pk": self.ou.pk, "employee_id": 999_999},
        )
        client = APIClient()
        client.force_authenticate(user=self.lead)
        r = client.delete(url)
        self.assertEqual(r.status_code, 404)
