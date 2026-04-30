from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.access.policies import PolicyDecision, policy_audit_payload, resolve_access
from apps.organizations.models import Organization, OrganizationMember
from apps.projects.models import Project, ProjectMember
from apps.projects.project_permissions import (
    compute_project_policy_decision,
    require_project_access,
    require_view_project,
)
from rest_framework.exceptions import PermissionDenied

User = get_user_model()


def _pd(*, allowed, level, reason, scope_id, subject_id, object_id):
    return PolicyDecision(
        allowed=allowed,
        access_level=level,
        reason=reason,
        scope_type="project",
        scope_id=scope_id,
        subject_id=subject_id,
        object_id=object_id,
    )


class ResolveProjectAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="paccess",
            email="paccess@example.com",
            password="pass12345",
        )
        self.org = Organization.objects.create(name="PA Org", slug="pa-org")
        OrganizationMember.objects.create(user=self.user, organization=self.org, is_active=True)
        self.project = Project.objects.create(
            organization=self.org,
            name="PA Project",
            created_by=self.user,
        )
        ProjectMember.objects.create(
            project=self.project,
            user=self.user,
            role=ProjectMember.ROLE_OWNER,
            is_active=True,
        )

    @patch("apps.projects.project_permissions.compute_project_policy_decision")
    def test_project_read_owner(self, compute):
        compute.return_value = _pd(
            allowed=True,
            level="manage",
            reason="membership_manage",
            scope_id=str(self.project.pk),
            subject_id=self.user.id,
            object_id=self.project.pk,
        )
        d = resolve_access(
            user=self.user,
            action="project.read",
            scope_type="project",
            scope_id=str(self.project.pk),
            resource=self.project,
        )
        self.assertTrue(d.allowed)
        self.assertEqual(d.access_level, "manage")
        self.assertEqual(d.scope_type, "project")
        self.assertEqual(d.scope_id, str(self.project.pk))

    @patch("apps.projects.project_permissions.compute_project_policy_decision")
    def test_project_read_denied_for_metadata_only(self, compute):
        compute.return_value = _pd(
            allowed=True,
            level="metadata",
            reason="permission:project.view_metadata",
            scope_id=str(self.project.pk),
            subject_id=self.user.id,
            object_id=self.project.pk,
        )
        d = resolve_access(
            user=self.user,
            action="project.read",
            scope_type="project",
            scope_id=str(self.project.pk),
            resource=self.project,
        )
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, "requires:project.read")

    @patch("apps.projects.project_permissions.compute_project_policy_decision")
    def test_project_view_metadata_observer(self, compute):
        compute.return_value = _pd(
            allowed=True,
            level="metadata",
            reason="permission:project.view_metadata",
            scope_id=str(self.project.pk),
            subject_id=self.user.id,
            object_id=self.project.pk,
        )
        d = resolve_access(
            user=self.user,
            action="project.view_metadata",
            scope_type="project",
            scope_id=str(self.project.pk),
            resource=self.project,
        )
        self.assertTrue(d.allowed)

    @patch("apps.projects.project_permissions.compute_project_policy_decision")
    def test_project_manage_members_requires_manage_level(self, compute):
        compute.return_value = _pd(
            allowed=True,
            level="write",
            reason="permission:project.edit",
            scope_id=str(self.project.pk),
            subject_id=self.user.id,
            object_id=self.project.pk,
        )
        d = resolve_access(
            user=self.user,
            action="project.manage_members",
            scope_type="project",
            scope_id=str(self.project.pk),
            resource=self.project,
        )
        self.assertFalse(d.allowed)
        self.assertIn("requires", d.reason)

    def test_unsupported_project_action(self):
        d = resolve_access(
            user=self.user,
            action="project.teleport",
            scope_type="project",
            scope_id=str(self.project.pk),
            resource=self.project,
        )
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, "unsupported_action")

    def test_policy_audit_payload_keys(self):
        d = _pd(
            allowed=True,
            level="read",
            reason="project_visibility",
            scope_id=str(self.project.pk),
            subject_id=self.user.id,
            object_id=self.project.pk,
        )
        payload = policy_audit_payload(d)
        self.assertEqual(
            set(payload.keys()),
            {"access_level", "reason", "scope_type", "scope_id"},
        )


class ProjectRequireHelpersIntegrationTests(TestCase):
    """Unmocked ladder via compute_project_policy_decision (uses real membership)."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="powner",
            email="powner@example.com",
            password="pass12345",
        )
        self.outsider = User.objects.create_user(
            username="pout",
            email="pout@example.com",
            password="pass12345",
        )
        self.org = Organization.objects.create(name="PI Org", slug="pi-org")
        OrganizationMember.objects.create(user=self.owner, organization=self.org, is_active=True)
        OrganizationMember.objects.create(user=self.outsider, organization=self.org, is_active=True)
        self.project = Project.objects.create(
            organization=self.org,
            name="PI Project",
            created_by=self.owner,
        )
        ProjectMember.objects.create(
            project=self.project,
            user=self.owner,
            role=ProjectMember.ROLE_OWNER,
            is_active=True,
        )

    def test_owner_compute_is_manage(self):
        d = compute_project_policy_decision(self.owner, self.project)
        self.assertTrue(d.allowed)
        self.assertEqual(d.access_level, "manage")

    def test_outsider_compute_denied(self):
        d = compute_project_policy_decision(self.outsider, self.project)
        self.assertFalse(d.allowed)
        self.assertEqual(d.access_level, "none")

    def test_require_view_project_owner(self):
        require_view_project(self.owner, self.project)

    def test_require_view_project_outsider_raises(self):
        with self.assertRaises(PermissionDenied):
            require_view_project(self.outsider, self.project)

    def test_require_project_access_update_owner(self):
        d = require_project_access(
            self.owner,
            self.project,
            "project.update",
            "no",
        )
        self.assertTrue(d.allowed)

    def test_project_create_org_member(self):
        d = resolve_access(
            user=self.owner,
            action="project.create",
            scope_type="project",
            resource=self.org,
        )
        self.assertTrue(d.allowed)
        self.assertIn(d.reason, ("permission:project.create", "organization_member"))
