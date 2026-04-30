from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from apps.access.policies import resolve_access, resolve_ai_workspace_access

User = get_user_model()


class ResolveAiWorkspaceAccessTests(TestCase):
    def test_anonymous_user_gets_no_access(self):
        decision = resolve_ai_workspace_access(viewer=AnonymousUser(), owner_user_id=42)
        self.assertFalse(decision.can_view_metadata)
        self.assertFalse(decision.can_view_content)
        self.assertEqual(decision.reason, "anonymous")

    def test_owner_gets_full_access(self):
        owner = User.objects.create_user(username="owner", email="owner@example.com", password="pass12345")
        decision = resolve_ai_workspace_access(viewer=owner, owner_user_id=owner.id)
        self.assertTrue(decision.can_view_metadata)
        self.assertTrue(decision.can_view_content)
        self.assertEqual(decision.reason, "self")

    def test_superuser_gets_full_access(self):
        admin = User.objects.create_user(username="root", email="root@example.com", password="pass12345")
        admin.is_superuser = True
        admin.save(update_fields=["is_superuser"])
        decision = resolve_ai_workspace_access(viewer=admin, owner_user_id=999)
        self.assertTrue(decision.can_view_metadata)
        self.assertTrue(decision.can_view_content)
        self.assertEqual(decision.reason, "superuser")

    @patch("apps.access.policies.access_resolver.has_permission")
    def test_content_permission_implies_full_access(self, has_permission):
        user = User.objects.create_user(username="viewer", email="viewer@example.com", password="pass12345")
        has_permission.side_effect = [True]

        decision = resolve_ai_workspace_access(viewer=user, owner_user_id=123)

        self.assertTrue(decision.can_view_metadata)
        self.assertTrue(decision.can_view_content)
        self.assertEqual(decision.reason, "permission:ai.workspace.view_content")
        has_permission.assert_called_once_with(
            user,
            "ai.workspace.view_content",
            scope_type="ai_workspace",
            scope_id="123",
        )

    @patch("apps.access.policies.access_resolver.has_permission")
    def test_metadata_permission_only(self, has_permission):
        user = User.objects.create_user(username="meta", email="meta@example.com", password="pass12345")
        has_permission.side_effect = [False, True]

        decision = resolve_ai_workspace_access(viewer=user, owner_user_id=123)

        self.assertTrue(decision.can_view_metadata)
        self.assertFalse(decision.can_view_content)
        self.assertEqual(decision.reason, "permission:ai.workspace.view_metadata")
        self.assertEqual(has_permission.call_count, 2)

    @patch("apps.access.policies.access_resolver.has_permission")
    def test_no_permission_denied(self, has_permission):
        user = User.objects.create_user(username="none", email="none@example.com", password="pass12345")
        has_permission.side_effect = [False, False]

        decision = resolve_ai_workspace_access(viewer=user, owner_user_id=123)

        self.assertFalse(decision.can_view_metadata)
        self.assertFalse(decision.can_view_content)
        self.assertEqual(decision.reason, "no_permission")

    @patch("apps.access.policies.access_resolver.has_permission")
    def test_resolve_access_returns_policy_decision_contract(self, has_permission):
        user = User.objects.create_user(username="contract", email="contract@example.com", password="pass12345")
        has_permission.side_effect = [False, True]

        decision = resolve_access(
            user=user,
            action="ai.workspace.view_metadata",
            scope_type="ai_workspace",
            scope_id="123",
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.access_level, "metadata")
        self.assertEqual(decision.reason, "permission:ai.workspace.view_metadata")
        self.assertEqual(decision.scope_type, "ai_workspace")
        self.assertEqual(decision.scope_id, "123")
        self.assertEqual(decision.subject_id, user.id)
        self.assertEqual(decision.object_id, 123)

    def test_resolve_access_rejects_unsupported_scope(self):
        user = User.objects.create_user(username="unsupported", email="unsupported@example.com", password="pass12345")
        decision = resolve_access(
            user=user,
            action="project.view",
            scope_type="warehouse",
            scope_id="10",
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.access_level, "none")
        self.assertEqual(decision.reason, "unsupported_policy_target")
