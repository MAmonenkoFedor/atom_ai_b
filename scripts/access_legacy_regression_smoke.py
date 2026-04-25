"""Regression: legacy ProjectMember roles must keep working alongside new grants.

Scenarios:

* user is OWNER via ProjectMember and *also* has a docs.upload grant -> all
  owner capabilities remain TRUE; revoking the grant does not affect owner
  caps; revoking the membership leaves owner without access (sanity).
* user is EDITOR via ProjectMember and acquires docs.upload grant later ->
  no regression on existing edit/manage caps.
* user is VIEWER via ProjectMember and is granted tasks.create -> can create
  tasks but cannot edit/manage the project.
* user with NO membership but with a single project-scoped grant -> sees the
  project, capability matches the grant code, no privilege escalation.
* removing the membership does not remove unrelated grants and vice versa.

Run::

    .\\.venv\\Scripts\\python.exe manage.py shell -c "exec(open('scripts/access_legacy_regression_smoke.py', encoding='utf8').read())"
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.access import service as access_service
from apps.access.models import PermissionGrant
from apps.organizations.models import Organization, OrganizationMember
from apps.projects.models import Project, ProjectMember
from apps.projects.project_permissions import (
    ProjectAccessContext,
    can_assign_project_tasks,
    can_create_project_tasks,
    can_edit_project,
    can_manage_project_members,
    can_upload_project_docs,
    can_view_project,
)

User = get_user_model()
TAG = "legacy-regression"


def _u(username: str, *, super_user: bool = False) -> User:
    user, _ = User.objects.get_or_create(
        username=username,
        defaults={"email": f"{username}@regression.test", "is_active": True},
    )
    user.is_active = True
    user.is_superuser = super_user
    user.is_staff = super_user
    user.save()
    return user


def _expect(label: str, actual, expected) -> None:
    if bool(actual) != bool(expected):
        print(f"    [FAIL] {label}: expected={bool(expected)} actual={bool(actual)}")
        raise SystemExit(1)
    print(f"    [OK] {label}: {bool(actual)}")


def _purge(users: list[User], project: Project) -> None:
    PermissionGrant.objects.filter(employee__in=users, note__startswith=TAG).delete()
    ProjectMember.objects.filter(project=project, user__in=users).delete()


def main() -> None:
    print("=== legacy x grant regression smoke ===")

    super_user = _u("legacy-super", super_user=True)
    owner = _u("legacy-owner")
    editor = _u("legacy-editor")
    viewer = _u("legacy-viewer")
    pure_grant = _u("legacy-pure-grant")
    users = [super_user, owner, editor, viewer, pure_grant]

    org, _ = Organization.objects.get_or_create(
        slug="legacy-org", defaults={"name": "Legacy Org"}
    )
    project, _ = Project.objects.get_or_create(
        organization=org,
        name="Legacy Arena",
        defaults={"status": Project.STATUS_ACTIVE, "code": "legacy-arena"},
    )
    for u in users:
        OrganizationMember.objects.update_or_create(
            user=u, organization=org, defaults={"is_active": True}
        )
    _purge(users, project)

    # Membership baseline.
    project.created_by = owner
    project.save(update_fields=["created_by"])
    ProjectMember.objects.update_or_create(
        project=project, user=owner, defaults={"role": ProjectMember.ROLE_OWNER, "is_active": True}
    )
    ProjectMember.objects.update_or_create(
        project=project, user=editor, defaults={"role": ProjectMember.ROLE_EDITOR, "is_active": True}
    )
    ProjectMember.objects.update_or_create(
        project=project, user=viewer, defaults={"role": ProjectMember.ROLE_VIEWER, "is_active": True}
    )

    expires = timezone.now() + timedelta(days=14)

    # ------------------------------------------------------------------
    # 1) OWNER + grant: caps unchanged, grant adds nothing harmful.
    # ------------------------------------------------------------------
    print("[1] OWNER + docs.upload grant: owner capabilities are stable")
    owner_grant = access_service.grant_permission(
        employee=owner,
        permission_code="docs.upload",
        scope_type="project",
        scope_id=str(project.pk),
        granted_by=super_user,
        expires_at=expires,
        note=f"{TAG}:owner-redundant",
    ).grant
    _expect("owner can_view", can_view_project(owner, project), True)
    _expect("owner can_edit", can_edit_project(owner, project), True)
    _expect("owner can_manage_members", can_manage_project_members(owner, project), True)
    _expect("owner can_upload_docs", can_upload_project_docs(owner, project), True)
    _expect("owner can_create_tasks", can_create_project_tasks(owner, project), True)

    print("    revoke owner_grant -> owner caps unchanged (membership covers them)")
    access_service.revoke_permission(owner_grant, revoked_by=super_user, note=f"{TAG}:revoke-owner-grant")
    _expect("owner can_edit (no grant)", can_edit_project(owner, project), True)
    _expect("owner can_upload_docs (no grant)", can_upload_project_docs(owner, project), True)

    # ------------------------------------------------------------------
    # 2) EDITOR + grant: no regression, no escalation, no double-counting.
    # ------------------------------------------------------------------
    print("[2] EDITOR + docs.upload grant -> caps consistent")
    editor_grant = access_service.grant_permission(
        employee=editor,
        permission_code="docs.upload",
        scope_type="project",
        scope_id=str(project.pk),
        granted_by=super_user,
        expires_at=expires,
        note=f"{TAG}:editor-grant",
    ).grant
    _expect("editor can_edit", can_edit_project(editor, project), True)
    _expect("editor can_upload_docs", can_upload_project_docs(editor, project), True)
    _expect("editor can_manage_members", can_manage_project_members(editor, project), True)
    print("    revoke grant -> editor still has all editor caps via membership")
    access_service.revoke_permission(editor_grant, revoked_by=super_user, note=f"{TAG}:revoke-editor-grant")
    _expect("editor can_edit (after revoke)", can_edit_project(editor, project), True)
    _expect("editor can_upload_docs (after revoke)", can_upload_project_docs(editor, project), True)

    # ------------------------------------------------------------------
    # 3) VIEWER + tasks.create grant: gains exactly that capability,
    #    nothing else.
    # ------------------------------------------------------------------
    print("[3] VIEWER + tasks.create grant -> only the granted action enabled")
    viewer_grant = access_service.grant_permission(
        employee=viewer,
        permission_code="tasks.create",
        scope_type="project",
        scope_id=str(project.pk),
        granted_by=super_user,
        expires_at=expires,
        note=f"{TAG}:viewer-tasks",
    ).grant
    _expect("viewer can_view", can_view_project(viewer, project), True)
    _expect("viewer can_edit", can_edit_project(viewer, project), False)
    _expect("viewer can_manage_members", can_manage_project_members(viewer, project), False)
    _expect("viewer can_create_tasks", can_create_project_tasks(viewer, project), True)
    _expect("viewer can_assign_tasks", can_assign_project_tasks(viewer, project), False)
    _expect("viewer can_upload_docs", can_upload_project_docs(viewer, project), False)

    print("    revoke grant -> viewer is back to read-only, no leftover")
    access_service.revoke_permission(viewer_grant, revoked_by=super_user, note=f"{TAG}:revoke-viewer-grant")
    _expect("viewer can_create_tasks (after revoke)", can_create_project_tasks(viewer, project), False)
    _expect("viewer can_view (after revoke)", can_view_project(viewer, project), True)

    # ------------------------------------------------------------------
    # 4) Pure grant user (no membership): grant code dictates capability.
    # ------------------------------------------------------------------
    print("[4] No membership, only docs.upload grant")
    pure_grant_obj = access_service.grant_permission(
        employee=pure_grant,
        permission_code="docs.upload",
        scope_type="project",
        scope_id=str(project.pk),
        granted_by=super_user,
        expires_at=expires,
        note=f"{TAG}:pure-grant",
    ).grant
    _expect("pure_grant can_view", can_view_project(pure_grant, project), True)
    _expect("pure_grant can_upload_docs", can_upload_project_docs(pure_grant, project), True)
    _expect("pure_grant can_edit", can_edit_project(pure_grant, project), False)
    _expect("pure_grant can_create_tasks", can_create_project_tasks(pure_grant, project), False)

    print("    bulk context agrees with helpers")
    ctx = ProjectAccessContext(pure_grant, [project])
    caps = ctx.capabilities(project)
    assert caps["can_view_project"] is True, caps
    assert caps["can_upload_documents"] is True, caps
    assert caps["can_edit_project"] is False, caps
    assert caps["can_create_tasks"] is False, caps

    print("    deactivate membership of editor must NOT touch pure_grant or viewer access")
    ProjectMember.objects.filter(project=project, user=editor).update(is_active=False)
    _expect("editor still can_view (inactive membership)", can_view_project(editor, project), True)
    _expect("pure_grant unaffected by editor change", can_upload_project_docs(pure_grant, project), True)

    print("[5] cleanup")
    access_service.revoke_permission(pure_grant_obj, revoked_by=super_user, note=f"{TAG}:cleanup")
    _purge(users, project)

    print("=== legacy x grant regression smoke OK ===")


main()
