from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.access.policies import PolicyDecision, resolve_access
from apps.organizations.models import Organization, OrganizationMember
from apps.projects.models import Project, ProjectMember
from apps.workspaces import data as workspace_data
from apps.workspaces.task_policy import (
    compute_workspace_task_policy_decision,
    require_workspace_task_access,
    require_workspace_task_read_or_metadata,
)
from rest_framework.exceptions import PermissionDenied

User = get_user_model()


def _pd(level: str, *, allowed: bool = True, scope_sid: str = "t-1"):
    return PolicyDecision(
        allowed=allowed,
        access_level=level,
        reason="test",
        scope_type="task",
        scope_id=scope_sid,
        subject_id=1,
        object_id=None,
    )


class ResolveTaskAccessTests(TestCase):
    @patch("apps.workspaces.task_policy.compute_workspace_task_policy_decision")
    def test_task_read_requires_read_level(self, compute):
        user = User.objects.create_user(username="tr1", email="tr1@example.com", password="pass12345")
        compute.return_value = _pd("metadata")
        d = resolve_access(
            user=user,
            action="task.read",
            scope_type="task",
            scope_id="t-1",
            resource=type("R", (), {"employee_id": "emp-1", "task": {"id": "t-1"}})(),
        )
        self.assertFalse(d.allowed)

    @patch("apps.workspaces.task_policy.compute_workspace_task_policy_decision")
    def test_task_read_allowed(self, compute):
        user = User.objects.create_user(username="tr2", email="tr2@example.com", password="pass12345")
        compute.return_value = _pd("read")
        d = resolve_access(
            user=user,
            action="task.read",
            scope_type="task",
            scope_id="t-1",
            resource=type("R", (), {"employee_id": "emp-1", "task": {"id": "t-1"}})(),
        )
        self.assertTrue(d.allowed)

    def test_task_unsupported_action(self):
        user = User.objects.create_user(username="tr3", email="tr3@example.com", password="pass12345")
        d = resolve_access(
            user=user,
            action="task.teleport",
            scope_type="task",
            scope_id="t-1",
            resource=type("R", (), {"employee_id": "emp-1", "task": {"id": "t-1"}})(),
        )
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, "unsupported_action")


class WorkspaceTaskPolicyIntegrationTests(TestCase):
    """Real employee bucket + optional project cap."""

    def setUp(self):
        self.user = User.objects.create_user(username="twu", email="twu@example.com", password="pass12345")
        self.org = Organization.objects.create(name="TW Org", slug="tw-org")
        OrganizationMember.objects.create(user=self.user, organization=self.org, is_active=True)
        self.project = Project.objects.create(
            organization=self.org,
            name="TW Project",
            created_by=self.user,
        )
        ProjectMember.objects.create(
            project=self.project,
            user=self.user,
            role=ProjectMember.ROLE_VIEWER,
            is_active=True,
        )
        self.employee_id = workspace_data.resolve_employee_id_for_username(self.user.username)

    def test_own_task_without_project_is_write(self):
        d = compute_workspace_task_policy_decision(
            user=self.user,
            employee_id=self.employee_id,
            task={"id": "t-local", "title": "x"},
        )
        self.assertTrue(d.allowed)
        self.assertEqual(d.access_level, "write")

    def test_project_linked_task_capped_by_project_access(self):
        d = compute_workspace_task_policy_decision(
            user=self.user,
            employee_id=self.employee_id,
            task={"id": "t-p", "project_id": str(self.project.pk)},
        )
        self.assertTrue(d.allowed)
        self.assertEqual(d.access_level, "read")

    def test_require_workspace_task_access_raises_for_other_bucket(self):
        outsider = User.objects.create_user(username="tout", email="tout@example.com", password="pass12345")
        OrganizationMember.objects.create(user=outsider, organization=self.org, is_active=True)
        with self.assertRaises(PermissionDenied):
            require_workspace_task_access(
                outsider,
                self.employee_id,
                "task.read",
                task_id=None,
            )


class WorkspaceTaskReadOrMetadataTests(TestCase):
    @patch("apps.access.policies.resolve_access")
    def test_falls_back_to_view_metadata(self, resolve_access):
        user = User.objects.create_user(username="trm", email="trm@example.com", password="pass12345")
        resolve_access.side_effect = [
            PolicyDecision(
                allowed=False,
                access_level="none",
                reason="requires:task.read",
                scope_type="task",
                scope_id="",
                subject_id=user.id,
                object_id=None,
            ),
            PolicyDecision(
                allowed=True,
                access_level="metadata",
                reason="workspace_task",
                scope_type="task",
                scope_id="",
                subject_id=user.id,
                object_id=None,
            ),
        ]
        d = require_workspace_task_read_or_metadata(user, "emp-x", task_id=None)
        self.assertTrue(d.allowed)
        self.assertEqual(d.access_level, "metadata")
        self.assertEqual(resolve_access.call_count, 2)
