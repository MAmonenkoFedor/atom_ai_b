from types import SimpleNamespace
from typing import Literal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.access.policies import PolicyDecision
from apps.chats.models import Chat
from apps.workspaces.models import WorkspaceCabinetDocument

User = get_user_model()


class AiChatWorkspacePrivacyTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username="workspace_owner",
            email="owner@example.com",
            password="pass12345",
        )
        self.viewer = User.objects.create_user(
            username="workspace_viewer",
            email="viewer@example.com",
            password="pass12345",
        )
        self.chat = Chat.objects.create(
            title="Privacy test chat",
            created_by=self.viewer,
            chat_scope=Chat.SCOPE_PERSONAL,
            chat_type=Chat.TYPE_GENERAL,
        )
        self.workspace_doc = WorkspaceCabinetDocument.objects.create(
            user=self.owner,
            title="Salary grid 2026",
            document_type="pdf",
            source=WorkspaceCabinetDocument.Source.EXTERNAL,
            external_href="https://example.test/private.pdf",
            owner_label="Owner",
        )
        self.client.force_authenticate(user=self.viewer)

    @staticmethod
    def _fake_llm_result(text: str = "ok") -> SimpleNamespace:
        return SimpleNamespace(
            text=text,
            provider="openrouter",
            model="gpt-test",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            cost_estimate=0.01,
        )

    def _post_completion(self):
        return self.client.post(
            "/api/ai/chat/completions",
            {
                "thread_id": self.chat.pk,
                "message": "Summarize this document",
                "context_type": "document",
                "context_id": f"doc-{self.workspace_doc.pk}",
            },
            format="json",
        )

    def _post_workspace_completion(self, context_id: str):
        return self.client.post(
            "/api/ai/chat/completions",
            {
                "thread_id": self.chat.pk,
                "message": "Summarize this workspace",
                "context_type": "workspace",
                "context_id": context_id,
            },
            format="json",
        )

    @staticmethod
    def _system_payload(messages) -> str:
        return "\n".join(msg.get("content", "") for msg in (messages or []) if msg.get("role") == "system")

    @staticmethod
    def _audit_calls(emit_audit_event, event_type: str):
        return [call for call in emit_audit_event.call_args_list if call.kwargs.get("event_type") == event_type]

    def _policy_decision(
        self,
        *,
        access_level: Literal["none", "metadata", "read", "write", "manage", "admin"],
        reason: str,
        owner_user_id: int | None = None,
    ) -> PolicyDecision:
        return PolicyDecision(
            allowed=access_level != "none",
            access_level=access_level,
            reason=reason,
            scope_type="ai_workspace",
            scope_id=str(owner_user_id or self.owner.id),
            subject_id=self.viewer.id,
            object_id=owner_user_id or self.owner.id,
        )

    @patch("apps.ai.api.views.emit_audit_event")
    @patch("apps.ai.api.views.resolve_access")
    def test_document_context_denied_without_permissions(self, resolve_access, emit_audit_event):
        resolve_access.return_value = self._policy_decision(access_level="none", reason="no_permission")

        response = self._post_completion()

        self.assertEqual(response.status_code, 403)
        self.assertIn("Недостаточно прав", str(response.data))
        denied_calls = self._audit_calls(emit_audit_event, "ai.workspace_content_access_denied")
        self.assertEqual(len(denied_calls), 1)
        self.assertEqual(
            denied_calls[0].kwargs.get("payload", {}).get("reason"),
            "no_permission",
        )

    @patch("apps.ai.api.views.emit_audit_event")
    @patch("apps.ai.api.views.AiChatCompletionsView.provider.chat_completions")
    @patch("apps.ai.api.views.resolve_access")
    def test_document_context_metadata_only_hides_title(
        self,
        resolve_access,
        chat_completions,
        emit_audit_event,
    ):
        resolve_access.return_value = self._policy_decision(
            access_level="metadata",
            reason="permission:ai.workspace.view_metadata",
        )
        captured_messages = {}

        def fake_chat_completions(*, messages, model, max_tokens):
            captured_messages["messages"] = messages
            return self._fake_llm_result("metadata-only")

        chat_completions.side_effect = fake_chat_completions

        response = self._post_completion()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["output_text"], "metadata-only")
        system_payload = self._system_payload(captured_messages.get("messages", []))
        self.assertIn("title=(hidden: requires ai.workspace.view_content)", system_payload)
        self.assertNotIn("Salary grid 2026", system_payload)
        metadata_calls = self._audit_calls(emit_audit_event, "ai.workspace_metadata_accessed")
        self.assertEqual(len(metadata_calls), 1)
        self.assertEqual(
            metadata_calls[0].kwargs.get("payload", {}).get("reason"),
            "permission:ai.workspace.view_metadata",
        )

    @patch("apps.ai.api.views.emit_audit_event")
    @patch("apps.ai.api.views.AiChatCompletionsView.provider.chat_completions")
    @patch("apps.ai.api.views.resolve_access")
    def test_document_context_content_access_includes_title(
        self,
        resolve_access,
        chat_completions,
        emit_audit_event,
    ):
        resolve_access.return_value = self._policy_decision(
            access_level="read",
            reason="permission:ai.workspace.view_content",
        )
        captured_messages = {}

        def fake_chat_completions(*, messages, model, max_tokens):
            captured_messages["messages"] = messages
            return self._fake_llm_result("full-content")

        chat_completions.side_effect = fake_chat_completions

        response = self._post_completion()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["output_text"], "full-content")
        system_payload = self._system_payload(captured_messages.get("messages", []))
        self.assertIn("title=Salary grid 2026", system_payload)
        content_calls = self._audit_calls(emit_audit_event, "ai.workspace_content_accessed")
        self.assertEqual(len(content_calls), 1)
        self.assertEqual(
            content_calls[0].kwargs.get("payload", {}).get("reason"),
            "permission:ai.workspace.view_content",
        )

    @patch("apps.ai.api.views.emit_audit_event")
    @patch("apps.ai.api.views.AiChatCompletionsView.provider.chat_completions")
    @patch("apps.ai.api.views.resolve_access")
    def test_owner_self_access_skips_policy_and_includes_title(
        self,
        resolve_access,
        chat_completions,
        emit_audit_event,
    ):
        self.client.force_authenticate(user=self.owner)
        chat = Chat.objects.create(
            title="Owner chat",
            created_by=self.owner,
            chat_scope=Chat.SCOPE_PERSONAL,
            chat_type=Chat.TYPE_GENERAL,
        )
        captured_messages = {}

        def fake_chat_completions(*, messages, model, max_tokens):
            captured_messages["messages"] = messages
            return self._fake_llm_result("owner-full-content")

        chat_completions.side_effect = fake_chat_completions

        response = self.client.post(
            "/api/ai/chat/completions",
            {
                "thread_id": chat.pk,
                "message": "Summarize my own document",
                "context_type": "document",
                "context_id": f"doc-{self.workspace_doc.pk}",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["output_text"], "owner-full-content")
        system_payload = self._system_payload(captured_messages.get("messages", []))
        self.assertIn("title=Salary grid 2026", system_payload)
        resolve_access.assert_not_called()
        metadata_events = self._audit_calls(emit_audit_event, "ai.workspace_metadata_accessed")
        denied_events = self._audit_calls(emit_audit_event, "ai.workspace_content_access_denied")
        self.assertEqual(len(metadata_events), 0)
        self.assertEqual(len(denied_events), 0)

    @patch("apps.ai.api.views.emit_audit_event")
    @patch("apps.ai.api.views.AiChatCompletionsView.provider.chat_completions")
    @patch("apps.ai.api.views.workspace_data.list_workspace_tasks")
    @patch("apps.ai.api.views.workspace_data.get_employee_owner_profile")
    @patch("apps.ai.api.views.workspace_data.resolve_employee_id_for_username")
    @patch("apps.ai.api.views.resolve_access")
    def test_workspace_context_metadata_only_hides_content(
        self,
        resolve_access,
        resolve_employee_id_for_username,
        get_employee_owner_profile,
        list_workspace_tasks,
        chat_completions,
        emit_audit_event,
    ):
        resolve_access.return_value = self._policy_decision(
            access_level="metadata",
            reason="permission:ai.workspace.view_metadata",
        )
        chat_completions.return_value = self._fake_llm_result("workspace-metadata")
        response = self._post_workspace_completion(str(self.owner.id))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(resolve_employee_id_for_username.called)
        self.assertFalse(get_employee_owner_profile.called)
        self.assertFalse(list_workspace_tasks.called)
        metadata_calls = self._audit_calls(emit_audit_event, "ai.workspace_metadata_accessed")
        self.assertEqual(len(metadata_calls), 1)
        self.assertEqual(
            metadata_calls[0].kwargs.get("payload", {}).get("mode"),
            "workspace_context",
        )
        self.assertEqual(response.data["output_text"], "workspace-metadata")
        chat_completions.assert_called_once()

    @patch("apps.ai.api.views.emit_audit_event")
    @patch("apps.ai.api.views.AiChatCompletionsView.provider.chat_completions")
    @patch("apps.ai.api.views.resolve_access")
    def test_workspace_context_denied_without_permissions(
        self,
        resolve_access,
        chat_completions,
        emit_audit_event,
    ):
        resolve_access.return_value = self._policy_decision(access_level="none", reason="no_permission")

        response = self._post_workspace_completion(str(self.owner.id))

        self.assertEqual(response.status_code, 403)
        self.assertIn("Недостаточно прав", str(response.data))
        chat_completions.assert_not_called()
        denied_calls = self._audit_calls(emit_audit_event, "ai.workspace_content_access_denied")
        self.assertEqual(len(denied_calls), 1)
        self.assertEqual(
            denied_calls[0].kwargs.get("payload", {}).get("reason"),
            "no_permission",
        )

    @patch("apps.ai.api.views.emit_audit_event")
    @patch("apps.ai.api.views.AiChatCompletionsView.provider.chat_completions")
    @patch("apps.ai.api.views.workspace_data.list_workspace_tasks")
    @patch("apps.ai.api.views.workspace_data.get_employee_owner_profile")
    @patch("apps.ai.api.views.workspace_data.resolve_employee_id_for_username")
    @patch("apps.ai.api.views.resolve_access")
    def test_workspace_context_content_access_includes_profile_name(
        self,
        resolve_access,
        resolve_employee_id_for_username,
        get_employee_owner_profile,
        list_workspace_tasks,
        chat_completions,
        emit_audit_event,
    ):
        resolve_access.return_value = self._policy_decision(
            access_level="read",
            reason="permission:ai.workspace.view_content",
        )
        resolve_employee_id_for_username.return_value = "emp-owner"
        get_employee_owner_profile.return_value = {
            "header": {"full_name": "Owner Full Name"},
            "projects": [{"id": "p1"}, {"id": "p2"}],
        }
        list_workspace_tasks.return_value = [{"id": "t1"}, {"id": "t2"}, {"id": "t3"}]
        chat_completions.return_value = self._fake_llm_result("workspace-content")

        response = self._post_workspace_completion(str(self.owner.id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["output_text"], "workspace-content")
        self.assertTrue(resolve_employee_id_for_username.called)
        self.assertTrue(get_employee_owner_profile.called)
        self.assertTrue(list_workspace_tasks.called)
        llm_messages = chat_completions.call_args.kwargs.get("messages", [])
        system_payload = self._system_payload(llm_messages)
        self.assertIn("profile_name=Owner Full Name", system_payload)
        self.assertIn("tasks_count=3", system_payload)
        self.assertIn("documents_count=2", system_payload)
        content_calls = self._audit_calls(emit_audit_event, "ai.workspace_content_accessed")
        self.assertEqual(len(content_calls), 1)
        self.assertEqual(
            content_calls[0].kwargs.get("payload", {}).get("reason"),
            "permission:ai.workspace.view_content",
        )

    def test_workspace_context_invalid_context_id_returns_400(self):
        response = self._post_workspace_completion("employee-abc")
        self.assertEqual(response.status_code, 400)
        self.assertIn("context_id", str(response.data))

    @patch("apps.ai.api.views.emit_audit_event")
    @patch("apps.ai.api.views.AiChatCompletionsView.provider.chat_completions")
    @patch("apps.ai.api.views.workspace_data.list_workspace_tasks")
    @patch("apps.ai.api.views.workspace_data.get_employee_owner_profile")
    @patch("apps.ai.api.views.workspace_data.resolve_employee_id_for_username")
    @patch("apps.ai.api.views.resolve_access")
    def test_workspace_context_me_self_access_skips_policy(
        self,
        resolve_access,
        resolve_employee_id_for_username,
        get_employee_owner_profile,
        list_workspace_tasks,
        chat_completions,
        emit_audit_event,
    ):
        self.client.force_authenticate(user=self.viewer)
        resolve_employee_id_for_username.return_value = "emp-viewer"
        get_employee_owner_profile.return_value = {
            "header": {"full_name": "Viewer Full Name"},
            "projects": [{"id": "p1"}],
        }
        list_workspace_tasks.return_value = [{"id": "t1"}]
        chat_completions.return_value = self._fake_llm_result("workspace-self")

        response = self._post_workspace_completion("me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["output_text"], "workspace-self")
        resolve_access.assert_not_called()
        llm_messages = chat_completions.call_args.kwargs.get("messages", [])
        system_payload = self._system_payload(llm_messages)
        self.assertIn(f"user_id={self.viewer.id}", system_payload)
        self.assertIn("profile_name=Viewer Full Name", system_payload)
        self.assertIn("tasks_count=1", system_payload)
        self.assertIn("documents_count=1", system_payload)

        denied_events = self._audit_calls(emit_audit_event, "ai.workspace_content_access_denied")
        metadata_events = self._audit_calls(emit_audit_event, "ai.workspace_metadata_accessed")
        self.assertEqual(len(denied_events), 0)
        self.assertEqual(len(metadata_events), 0)
