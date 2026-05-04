from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.access.policies import PolicyDecision, policy_audit_payload, resolve_access
from apps.organizations.models import Organization, OrganizationMember
from apps.orgstructure.models import OrgUnit
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

    @patch("apps.projects.project_permissions.compute_project_policy_decision")
    def test_project_manage_settings_requires_manage_level(self, compute):
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
            action="project.manage_settings",
            scope_type="project",
            scope_id=str(self.project.pk),
            resource=self.project,
        )
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, "requires:project.manage_settings")

    @patch("apps.projects.project_permissions.compute_project_policy_decision")
    def test_project_manage_settings_allowed_for_manage(self, compute):
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
            action="project.manage_settings",
            scope_type="project",
            scope_id=str(self.project.pk),
            resource=self.project,
        )
        self.assertTrue(d.allowed)

    @patch("apps.projects.project_permissions.compute_project_policy_decision")
    def test_project_update_allows_write_level(self, compute):
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
            action="project.update",
            scope_type="project",
            scope_id=str(self.project.pk),
            resource=self.project,
        )
        self.assertTrue(d.allowed)

    @patch("apps.projects.project_permissions.compute_project_policy_decision")
    def test_project_delete_denied_for_write_level(self, compute):
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
            action="project.delete",
            scope_type="project",
            scope_id=str(self.project.pk),
            resource=self.project,
        )
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, "requires:project.delete")

    @patch("apps.projects.project_permissions.compute_project_policy_decision")
    def test_project_delete_allowed_for_manage_level(self, compute):
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
            action="project.delete",
            scope_type="project",
            scope_id=str(self.project.pk),
            resource=self.project,
        )
        self.assertTrue(d.allowed)

    @patch("apps.projects.project_permissions.has_project_access_permission")
    @patch("apps.projects.project_permissions.compute_project_policy_decision")
    def test_project_delete_allowed_with_explicit_grant_at_write(
        self, compute, has_perm
    ):
        compute.return_value = _pd(
            allowed=True,
            level="write",
            reason="permission:project.edit",
            scope_id=str(self.project.pk),
            subject_id=self.user.id,
            object_id=self.project.pk,
        )
        has_perm.return_value = True
        d = resolve_access(
            user=self.user,
            action="project.delete",
            scope_type="project",
            scope_id=str(self.project.pk),
            resource=self.project,
        )
        self.assertTrue(d.allowed)
        has_perm.assert_called_once_with(self.user, self.project, "project.delete")

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

    def test_project_create_denied_without_explicit_permission(self):
        d = resolve_access(
            user=self.owner,
            action="project.create",
            scope_type="project",
            resource=self.org,
        )
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, "requires:project.create")

    @patch("apps.access.policies.access_resolver.has_permission")
    def test_project_create_allowed_when_permission_granted(self, has_permission):
        has_permission.return_value = True
        d = resolve_access(
            user=self.owner,
            action="project.create",
            scope_type="project",
            resource=self.org,
        )
        self.assertTrue(d.allowed)
        self.assertEqual(d.reason, "permission:project.create")
        has_permission.assert_called_once_with(
            self.owner,
            "project.create",
            scope_type="company",
            scope_id=str(self.org.pk),
        )


class ProjectDestroyApiIntegrationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="pdel_owner",
            email="pdel_owner@example.com",
            password="pass12345",
        )
        self.viewer = User.objects.create_user(
            username="pdel_viewer",
            email="pdel_viewer@example.com",
            password="pass12345",
        )
        self.org = Organization.objects.create(name="PDel Org", slug="pdel-org")
        OrganizationMember.objects.create(user=self.owner, organization=self.org, is_active=True)
        OrganizationMember.objects.create(user=self.viewer, organization=self.org, is_active=True)

    def test_delete_as_owner_returns_204(self):
        project = Project.objects.create(
            organization=self.org,
            name="To Delete",
            created_by=self.owner,
        )
        ProjectMember.objects.create(
            project=project,
            user=self.owner,
            role=ProjectMember.ROLE_OWNER,
            is_active=True,
        )
        url = reverse("projects-detail", kwargs={"pk": project.pk})
        client = APIClient()
        client.force_authenticate(user=self.owner)
        response = client.delete(url)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())

    def test_delete_as_viewer_returns_403(self):
        project = Project.objects.create(
            organization=self.org,
            name="Viewer Delete",
            created_by=self.owner,
        )
        ProjectMember.objects.create(
            project=project,
            user=self.owner,
            role=ProjectMember.ROLE_OWNER,
            is_active=True,
        )
        ProjectMember.objects.create(
            project=project,
            user=self.viewer,
            role=ProjectMember.ROLE_VIEWER,
            is_active=True,
        )
        url = reverse("projects-detail", kwargs={"pk": project.pk})
        client = APIClient()
        client.force_authenticate(user=self.viewer)
        response = client.delete(url)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Project.objects.filter(pk=project.pk).exists())


class ProjectPatchP11ApiTests(TestCase):
    """P1.1 PATCH split: update vs manage_settings, audit, viewer denied."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="patchp11",
            email="patchp11@example.com",
            password="pass12345",
        )
        self.viewer = User.objects.create_user(
            username="patchp11v",
            email="patchp11v@example.com",
            password="pass12345",
        )
        self.org = Organization.objects.create(name="PP11 Org", slug="pp11-org")
        OrganizationMember.objects.create(user=self.user, organization=self.org, is_active=True)
        OrganizationMember.objects.create(user=self.viewer, organization=self.org, is_active=True)
        self.ou = OrgUnit.objects.create(organization=self.org, name="Dept A", code="depta")
        self.project = Project.objects.create(
            organization=self.org,
            name="PP11 Project",
            created_by=self.user,
            project_settings={"visibility": "public"},
        )
        ProjectMember.objects.create(
            project=self.project,
            user=self.user,
            role=ProjectMember.ROLE_CONTRIBUTOR,
            is_active=True,
        )
        ProjectMember.objects.create(
            project=self.project,
            user=self.viewer,
            role=ProjectMember.ROLE_VIEWER,
            is_active=True,
        )
        self.url = reverse("projects-detail", kwargs={"pk": self.project.pk})

    def test_patch_viewer_ordinary_forbidden(self):
        client = APIClient()
        client.force_authenticate(user=self.viewer)
        r = client.patch(self.url, {"name": "Renamed"}, format="json")
        self.assertEqual(r.status_code, 403)

    @patch("apps.projects.project_permissions.compute_project_policy_decision")
    def test_patch_write_ordinary_ok(self, compute):
        compute.return_value = _pd(
            allowed=True,
            level="write",
            reason="permission:project.edit",
            scope_id=str(self.project.pk),
            subject_id=self.user.id,
            object_id=self.project.pk,
        )
        client = APIClient()
        client.force_authenticate(user=self.user)
        r = client.patch(self.url, {"name": "Write OK", "public_summary": "Summary"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data.get("name"), "Write OK")
        self.assertEqual(r.data.get("public_summary"), "Summary")

    @patch("apps.projects.project_permissions.compute_project_policy_decision")
    def test_patch_write_settings_forbidden(self, compute):
        compute.return_value = _pd(
            allowed=True,
            level="write",
            reason="permission:project.edit",
            scope_id=str(self.project.pk),
            subject_id=self.user.id,
            object_id=self.project.pk,
        )
        client = APIClient()
        client.force_authenticate(user=self.user)
        r = client.patch(self.url, {"primary_org_unit": self.ou.pk}, format="json")
        self.assertEqual(r.status_code, 403)

    @patch("apps.projects.project_permissions.compute_project_policy_decision")
    def test_patch_manage_settings_ok(self, compute):
        compute.return_value = _pd(
            allowed=True,
            level="manage",
            reason="membership_manage",
            scope_id=str(self.project.pk),
            subject_id=self.user.id,
            object_id=self.project.pk,
        )
        client = APIClient()
        client.force_authenticate(user=self.user)
        r = client.patch(
            self.url,
            {
                "primary_org_unit": self.ou.pk,
                "settings": {"workflow": "kanban", "visibility": "internal"},
            },
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data.get("primary_org_unit_id"), self.ou.pk)
        self.assertEqual(r.data.get("settings", {}).get("workflow"), "kanban")
        self.assertEqual(r.data.get("settings", {}).get("visibility"), "internal")

    @patch("apps.projects.api.views.emit_audit_event")
    @patch("apps.projects.project_permissions.compute_project_policy_decision")
    def test_patch_sensitive_emits_settings_and_visibility_audits(self, compute, emit):
        compute.return_value = _pd(
            allowed=True,
            level="manage",
            reason="membership_manage",
            scope_id=str(self.project.pk),
            subject_id=self.user.id,
            object_id=self.project.pk,
        )
        client = APIClient()
        client.force_authenticate(user=self.user)
        client.patch(
            self.url,
            {"settings": {"visibility": "internal"}},
            format="json",
        )
        types = [c.kwargs.get("event_type") for c in emit.call_args_list]
        self.assertIn("project.updated", types)
        self.assertIn("project.settings_updated", types)
        self.assertIn("project.visibility_changed", types)
        updated_payload = emit.call_args_list[0].kwargs.get("payload") or {}
        self.assertIn("changed_fields", updated_payload)
        self.assertIn("sensitive_fields", updated_payload)
        self.assertIn("access_level", updated_payload)
