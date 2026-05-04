"""resolve_access for scope_type=department."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.access.policies import PolicyDecision, resolve_access
from apps.organizations.models import Organization, OrganizationMember
from apps.orgstructure.models import OrgUnit

User = get_user_model()


def _pd(*, allowed, level, reason, scope_id, subject_id, object_id):
    return PolicyDecision(
        allowed=allowed,
        access_level=level,
        reason=reason,
        scope_type="department",
        scope_id=scope_id,
        subject_id=subject_id,
        object_id=object_id,
    )


class ResolveDepartmentAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="daccess",
            email="daccess@example.com",
            password="pass12345",
        )
        self.org = Organization.objects.create(name="D Org", slug="d-org")
        OrganizationMember.objects.create(user=self.user, organization=self.org, is_active=True)
        self.ou = OrgUnit.objects.create(organization=self.org, name="D Unit", code="du")

    @patch("apps.orgstructure.department_permissions.compute_department_policy_decision")
    def test_department_read_requires_read_level(self, compute):
        compute.return_value = _pd(
            allowed=True,
            level="metadata",
            reason="permission:department.view_metadata",
            scope_id=str(self.ou.pk),
            subject_id=self.user.id,
            object_id=self.ou.pk,
        )
        d = resolve_access(
            user=self.user,
            action="department.read",
            scope_type="department",
            scope_id=str(self.ou.pk),
            resource=self.ou,
        )
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, "requires:department.read")

    @patch("apps.orgstructure.department_permissions.compute_department_policy_decision")
    def test_department_read_allowed(self, compute):
        compute.return_value = _pd(
            allowed=True,
            level="read",
            reason="department_membership",
            scope_id=str(self.ou.pk),
            subject_id=self.user.id,
            object_id=self.ou.pk,
        )
        d = resolve_access(
            user=self.user,
            action="department.read",
            scope_type="department",
            scope_id=str(self.ou.pk),
            resource=self.ou,
        )
        self.assertTrue(d.allowed)

    def test_department_invalid_scope(self):
        d = resolve_access(
            user=self.user,
            action="department.read",
            scope_type="department",
            scope_id="999999",
            resource=None,
        )
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, "invalid_department")
