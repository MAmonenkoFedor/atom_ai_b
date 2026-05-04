from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.access.policies import resolve_access
from apps.organizations.models import Organization
from apps.orgstructure.models import OrgUnit
from apps.projects.models import Project

User = get_user_model()


class ResolveDocumentAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="doc_user",
            email="doc_user@example.com",
            password="pass12345",
        )
        self.org = Organization.objects.create(name="Org", slug="org-doc-tests")
        self.project = Project.objects.create(
            organization=self.org,
            name="Doc Project",
            created_by=self.user,
        )

    @patch("apps.projects.project_permissions.can_upload_project_docs")
    @patch("apps.projects.project_permissions.can_view_project_docs")
    def test_project_document_read_allowed_with_view_permission(self, can_view_project_docs, can_upload_project_docs):
        can_upload_project_docs.return_value = False
        can_view_project_docs.return_value = True

        decision = resolve_access(
            user=self.user,
            action="document.read",
            scope_type="document",
            scope_id=str(self.project.id),
            resource=self.project,
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.access_level, "read")
        self.assertEqual(decision.reason, "permission:project.docs.view")

    @patch("apps.projects.project_permissions.can_upload_project_docs")
    @patch("apps.projects.project_permissions.can_view_project_docs")
    def test_project_document_upload_denied_with_only_view_permission(
        self,
        can_view_project_docs,
        can_upload_project_docs,
    ):
        can_upload_project_docs.return_value = False
        can_view_project_docs.return_value = True

        decision = resolve_access(
            user=self.user,
            action="document.upload",
            scope_type="document",
            scope_id=str(self.project.id),
            resource=self.project,
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "requires:document.upload")

    @patch("apps.projects.project_permissions.can_upload_project_docs")
    @patch("apps.projects.project_permissions.can_view_project_docs")
    def test_project_document_share_allowed_with_manage_permission(
        self,
        can_view_project_docs,
        can_upload_project_docs,
    ):
        can_upload_project_docs.return_value = True
        can_view_project_docs.return_value = True

        decision = resolve_access(
            user=self.user,
            action="document.share",
            scope_type="document",
            scope_id=str(self.project.id),
            resource=self.project,
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.access_level, "write")
        self.assertEqual(decision.reason, "permission:project.docs.upload")

    @patch("apps.access.policies.access_resolver.has_permission")
    def test_workspace_document_metadata_only(self, has_permission):
        # Per resolve_access call:
        # 1) ai.workspace.view_content -> False, ai.workspace.view_metadata -> True
        # 2) ai.workspace.view_content -> False, ai.workspace.view_metadata -> True
        has_permission.side_effect = [False, True, False, True]
        workspace_doc = SimpleNamespace(user_id=999, id=77)

        metadata_decision = resolve_access(
            user=self.user,
            action="document.view_metadata",
            scope_type="document",
            scope_id="999",
            resource=workspace_doc,
        )
        content_decision = resolve_access(
            user=self.user,
            action="document.read",
            scope_type="document",
            scope_id="999",
            resource=workspace_doc,
        )

        self.assertTrue(metadata_decision.allowed)
        self.assertEqual(metadata_decision.access_level, "metadata")
        self.assertFalse(content_decision.allowed)
        self.assertEqual(content_decision.reason, "requires:document.read")

    def test_document_unsupported_action_denied(self):
        decision = resolve_access(
            user=self.user,
            action="document.publish",
            scope_type="document",
            scope_id=str(self.project.id),
            resource=self.project,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "unsupported_action")

    @patch("apps.orgstructure.department_permissions.get_department_membership")
    @patch("apps.access.policies.access_resolver.has_permission")
    def test_department_document_read_via_membership(self, has_permission, get_membership):
        ou = OrgUnit.objects.create(organization=self.org, name="DeptDoc", code="dd")
        has_permission.return_value = False
        get_membership.return_value = SimpleNamespace()

        decision = resolve_access(
            user=self.user,
            action="document.read",
            scope_type="document",
            scope_id=str(ou.pk),
            resource=ou,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.access_level, "read")
        self.assertEqual(decision.reason, "department_membership")

    @patch("apps.orgstructure.department_permissions.has_department_access_permission")
    @patch("apps.access.policies.access_resolver.has_permission")
    def test_department_document_upload_via_manage_documents(self, has_permission, has_department_access):
        ou = OrgUnit.objects.create(organization=self.org, name="DeptDoc2", code="dd2")
        has_department_access.return_value = True
        has_permission.return_value = False

        decision = resolve_access(
            user=self.user,
            action="document.upload",
            scope_type="document",
            scope_id=str(ou.pk),
            resource=ou,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.access_level, "write")
        self.assertEqual(decision.reason, "permission:department.manage_documents")
