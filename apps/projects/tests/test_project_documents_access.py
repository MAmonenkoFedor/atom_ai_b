from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.organizations.models import Organization
from apps.projects.models import Project, ProjectDocument
from apps.projects.project_documents import list_project_documents

User = get_user_model()


class ProjectDocumentsAccessTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="docs_user",
            email="docs_user@example.com",
            password="pass12345",
        )
        self.org = Organization.objects.create(name="Docs Org", slug="docs-org")
        self.project = Project.objects.create(
            organization=self.org,
            name="Docs Project",
            created_by=self.user,
        )
        self.doc = ProjectDocument.objects.create(
            project=self.project,
            uploaded_by=self.user,
            title="Private spec",
            document_type="doc",
            source=ProjectDocument.Source.EXTERNAL,
            external_href="https://example.test/spec",
            owner_label="Owner",
        )

    def _request(self):
        request = self.factory.get("/api/projects/1/documents")
        request.user = self.user
        return request

    @patch("apps.projects.project_documents.resolve_access")
    def test_returns_metadata_only_when_no_read_but_metadata_allowed(self, resolve_access):
        resolve_access.side_effect = [
            # read decision
            type("Decision", (), {"allowed": False})(),
            # metadata decision
            type("Decision", (), {"allowed": True})(),
        ]

        rows = list_project_documents(self._request(), self.project)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Private spec")
        self.assertEqual(rows[0]["href"], "")

    @patch("apps.projects.project_documents.resolve_access")
    def test_returns_full_content_when_read_allowed(self, resolve_access):
        resolve_access.return_value = type("Decision", (), {"allowed": True})()

        rows = list_project_documents(self._request(), self.project)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Private spec")
        self.assertIn("example.test/spec", rows[0]["href"])
