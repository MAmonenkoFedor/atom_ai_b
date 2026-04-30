from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.workspaces.documents_service import list_workspace_documents
from apps.workspaces.models import WorkspaceCabinetDocument

User = get_user_model()


class WorkspaceCabinetDocumentsAccessTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="cab_user",
            email="cab_user@example.com",
            password="pass12345",
        )
        self.doc = WorkspaceCabinetDocument.objects.create(
            user=self.user,
            title="Private link",
            document_type="link",
            source=WorkspaceCabinetDocument.Source.EXTERNAL,
            external_href="https://example.test/ws-doc",
            owner_label="Me",
        )

    def _request(self):
        request = self.factory.get("/api/me/workspace")
        request.user = self.user
        return request

    @patch("apps.workspaces.documents_service.resolve_access")
    def test_returns_metadata_only_when_no_read_but_metadata_allowed(self, resolve_access):
        resolve_access.side_effect = [
            type("Decision", (), {"allowed": False})(),
            type("Decision", (), {"allowed": True})(),
        ]

        rows = list_workspace_documents(self._request())

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Private link")
        self.assertEqual(rows[0]["href"], "")

    @patch("apps.workspaces.documents_service.resolve_access")
    def test_returns_full_content_when_read_allowed(self, resolve_access):
        resolve_access.return_value = type("Decision", (), {"allowed": True})()

        rows = list_workspace_documents(self._request())

        self.assertEqual(len(rows), 1)
        self.assertIn("example.test/ws-doc", rows[0]["href"])
