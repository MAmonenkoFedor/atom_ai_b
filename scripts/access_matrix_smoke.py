"""Access matrix smoke for project-scoped permissions.

Builds a small fixture: organisation + 2 projects (arena, olympus) and seven
user archetypes:

* ``super`` — system superuser
* ``owner`` — explicit project owner via ProjectMember
* ``editor`` — legacy manage role via ProjectMember
* ``viewer`` — passive ProjectMember
* ``grant_only`` — *no* membership, only a project-scoped ``docs.upload`` grant
* ``delegate`` — receives ``docs.upload`` via parent_grant from the owner
* ``stranger`` — nothing

For every archetype we evaluate:

* can_view_project
* can_edit_project
* can_manage_project_members
* can_upload_project_docs
* can_create_project_tasks
* can_assign_project_tasks
* can_change_project_task_deadline
* can_moderate_project_chat

…and assert the policy outcome matches the expected matrix.

Run::

    .\\.venv\\Scripts\\python.exe manage.py shell -c "exec(open('scripts/access_matrix_smoke.py', encoding='utf8').read())"
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.access import service as access_service
from apps.access.models import PermissionGrant
from apps.identity.models import Role, UserRole
from apps.organizations.models import Organization, OrganizationMember
from apps.projects.models import Project, ProjectMember
from apps.projects.project_permissions import (
    ProjectAccessContext,
    can_assign_project_tasks,
    can_block_project_tasks,
    can_change_project_task_deadline,
    can_create_project_tasks,
    can_edit_project,
    can_manage_project_members,
    can_moderate_project_chat,
    can_upload_project_docs,
    can_view_project,
)

User = get_user_model()


SUITE_TAG = "matrix-smoke"


def _u(username: str, *, super_user: bool = False) -> User:
    user, _ = User.objects.get_or_create(
        username=username,
        defaults={"email": f"{username}@matrix.test", "is_active": True},
    )
    user.is_active = True
    user.is_staff = super_user
    user.is_superuser = super_user
    user.save()
    return user


def _ensure_org_membership(user: User, org: Organization) -> None:
    OrganizationMember.objects.update_or_create(
        user=user,
        organization=org,
        defaults={"is_active": True},
    )


def _ensure_member(project: Project, user: User, role: str) -> ProjectMember:
    member, _ = ProjectMember.objects.update_or_create(
        project=project, user=user, defaults={"role": role, "is_active": True}
    )
    return member


def _purge(users: list[User], projects: list[Project]) -> None:
    PermissionGrant.objects.filter(employee__in=users, note__startswith=SUITE_TAG).delete()
    ProjectMember.objects.filter(project__in=projects, user__in=users).delete()


def _expect(label: str, actual, expected) -> None:
    if bool(actual) != bool(expected):
        print(f"    [FAIL] {label}: expected={bool(expected)} actual={bool(actual)}")
        raise SystemExit(1)
    print(f"    [OK] {label}: {bool(actual)}")


def _evaluate(label: str, user: User, project: Project, expected: dict) -> None:
    print(f"-- {label} --")
    _expect("can_view_project", can_view_project(user, project), expected["view"])
    _expect("can_edit_project", can_edit_project(user, project), expected["edit"])
    _expect(
        "can_manage_project_members",
        can_manage_project_members(user, project),
        expected["members"],
    )
    _expect(
        "can_upload_project_docs",
        can_upload_project_docs(user, project),
        expected["docs"],
    )
    _expect(
        "can_create_project_tasks",
        can_create_project_tasks(user, project),
        expected["tasks_create"],
    )
    _expect(
        "can_assign_project_tasks",
        can_assign_project_tasks(user, project),
        expected["tasks_assign"],
    )
    _expect(
        "can_change_project_task_deadline",
        can_change_project_task_deadline(user, project),
        expected["tasks_deadline"],
    )
    _expect(
        "can_block_project_tasks",
        can_block_project_tasks(user, project),
        expected["tasks_block"],
    )
    _expect(
        "can_moderate_project_chat",
        can_moderate_project_chat(user, project),
        expected["chat"],
    )

    # Bulk resolver must produce the exact same answers — guards against the
    # serializer drifting from the standalone helpers.
    ctx = ProjectAccessContext(user, [project])
    caps = ctx.capabilities(project)
    assert caps["can_view_project"] == expected["view"], caps
    assert caps["can_edit_project"] == expected["edit"], caps
    assert caps["can_upload_documents"] == expected["docs"], caps
    assert caps["can_create_tasks"] == expected["tasks_create"], caps
    assert caps["can_manage_members"] == expected["members"], caps
    assert caps["can_moderate_chat"] == expected["chat"], caps


def main() -> None:
    print("=== access matrix smoke ===")

    super_user = _u("matrix-super", super_user=True)
    owner = _u("matrix-owner")
    editor = _u("matrix-editor")
    viewer = _u("matrix-viewer")
    grant_only = _u("matrix-grant-only")
    delegate = _u("matrix-delegate")
    stranger = _u("matrix-stranger")
    all_users = [super_user, owner, editor, viewer, grant_only, delegate, stranger]

    org, _ = Organization.objects.get_or_create(
        slug="matrix-org",
        defaults={"name": "Matrix Org"},
    )
    arena, _ = Project.objects.get_or_create(
        organization=org,
        name="Matrix Arena",
        defaults={"status": Project.STATUS_ACTIVE, "code": "matrix-arena"},
    )
    olympus, _ = Project.objects.get_or_create(
        organization=org,
        name="Matrix Olympus",
        defaults={"status": Project.STATUS_ACTIVE, "code": "matrix-olympus"},
    )
    for u in all_users:
        _ensure_org_membership(u, org)

    super_role, _ = Role.objects.get_or_create(
        code="super_admin", defaults={"name": "Super Admin"}
    )
    UserRole.objects.update_or_create(
        user=super_user, role=super_role, organization=None, defaults={}
    )

    _purge(all_users, [arena, olympus])
    arena.created_by = owner
    arena.save(update_fields=["created_by"])

    _ensure_member(arena, owner, ProjectMember.ROLE_OWNER)
    _ensure_member(arena, editor, ProjectMember.ROLE_EDITOR)
    _ensure_member(arena, viewer, ProjectMember.ROLE_VIEWER)

    print("[1] grant_only: docs.upload @ project:arena")
    grant_for_only = access_service.grant_permission(
        employee=grant_only,
        permission_code="docs.upload",
        scope_type="project",
        scope_id=str(arena.pk),
        grant_mode=PermissionGrant.GRANT_MODE_USE_ONLY,
        granted_by=super_user,
        note=f"{SUITE_TAG}:grant_only",
    ).grant

    print("[2] owner gets project.assign_rights use_and_delegate, delegates docs.upload")
    parent = access_service.grant_permission(
        employee=owner,
        permission_code="project.assign_rights",
        scope_type="project",
        scope_id=str(arena.pk),
        grant_mode=PermissionGrant.GRANT_MODE_USE_AND_DELEGATE,
        granted_by=super_user,
        expires_at=timezone.now() + timedelta(days=14),
        note=f"{SUITE_TAG}:owner-rights",
    ).grant
    parent_docs = access_service.grant_permission(
        employee=owner,
        permission_code="docs.upload",
        scope_type="project",
        scope_id=str(arena.pk),
        grant_mode=PermissionGrant.GRANT_MODE_USE_AND_DELEGATE,
        granted_by=super_user,
        expires_at=timezone.now() + timedelta(days=14),
        note=f"{SUITE_TAG}:owner-docs",
    ).grant
    delegated_grant = access_service.grant_permission(
        employee=delegate,
        permission_code="docs.upload",
        scope_type="project",
        scope_id=str(arena.pk),
        grant_mode=PermissionGrant.GRANT_MODE_USE_ONLY,
        granted_by=owner,
        parent_grant=parent_docs,
        source_type=PermissionGrant.SOURCE_DELEGATION,
        expires_at=timezone.now() + timedelta(days=7),
        note=f"{SUITE_TAG}:delegate",
    ).grant

    # ---- expected matrix ----------------------------------------------------

    expected_super = dict(
        view=True, edit=True, members=True, docs=True,
        tasks_create=True, tasks_assign=True, tasks_deadline=True,
        tasks_block=True, chat=True,
    )
    expected_owner = dict(
        view=True, edit=True, members=True, docs=True,
        tasks_create=True, tasks_assign=True, tasks_deadline=True,
        tasks_block=True, chat=True,
    )
    expected_editor = dict(
        view=True, edit=True, members=True, docs=True,
        tasks_create=True, tasks_assign=True, tasks_deadline=True,
        tasks_block=True, chat=True,
    )
    expected_viewer = dict(
        view=True, edit=False, members=False, docs=False,
        tasks_create=False, tasks_assign=False, tasks_deadline=False,
        tasks_block=False, chat=False,
    )
    expected_grant_only = dict(
        view=True, edit=False, members=False, docs=True,
        tasks_create=False, tasks_assign=False, tasks_deadline=False,
        tasks_block=False, chat=False,
    )
    expected_delegate = dict(
        view=True, edit=False, members=False, docs=True,
        tasks_create=False, tasks_assign=False, tasks_deadline=False,
        tasks_block=False, chat=False,
    )
    expected_stranger = dict(
        view=False, edit=False, members=False, docs=False,
        tasks_create=False, tasks_assign=False, tasks_deadline=False,
        tasks_block=False, chat=False,
    )

    _evaluate("super (arena)", super_user, arena, expected_super)
    _evaluate("owner (arena)", owner, arena, expected_owner)
    _evaluate("editor (arena)", editor, arena, expected_editor)
    _evaluate("viewer (arena)", viewer, arena, expected_viewer)
    _evaluate("grant_only (arena)", grant_only, arena, expected_grant_only)
    _evaluate("delegate (arena)", delegate, arena, expected_delegate)
    _evaluate("stranger (arena)", stranger, arena, expected_stranger)

    print("-- isolation: grant on arena does not bleed into olympus --")
    _expect("grant_only sees olympus", can_view_project(grant_only, olympus), False)
    _expect("delegate sees olympus", can_view_project(delegate, olympus), False)

    print("[3] revoke parent -> cascade -> delegate loses access")
    access_service.revoke_permission(
        parent_docs,
        revoked_by=super_user,
        note=f"{SUITE_TAG}:cascade",
    )
    delegated_grant.refresh_from_db()
    assert delegated_grant.status == PermissionGrant.STATUS_REVOKED
    _expect(
        "delegate after cascade",
        can_upload_project_docs(delegate, arena),
        False,
    )

    print("[4] cleanup")
    access_service.revoke_permission(grant_for_only, revoked_by=super_user, note=f"{SUITE_TAG}:cleanup")
    access_service.revoke_permission(parent, revoked_by=super_user, note=f"{SUITE_TAG}:cleanup")
    _purge(all_users, [arena, olympus])

    print("=== access matrix smoke OK ===")


main()
