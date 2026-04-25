"""HTTP matrix smoke for access-control gating on real DRF endpoints.

The previous in-process matrix verifies the helpers; this one verifies the
end-to-end pipeline (auth -> permission classes -> queryset filter ->
serializer payload -> action gating) against the actual URL routes.

Archetypes covered:

* ``super`` — system superuser + super_admin role
* ``owner`` — project member with ROLE_OWNER
* ``viewer`` — project member with ROLE_VIEWER
* ``grant_only`` — no membership, only ``docs.upload`` grant @ project
* ``stranger`` — no membership, no grant

Endpoints checked:

* ``GET  /api/v1/projects/<id>``                  (visibility)
* ``PATCH /api/v1/projects/<id>``                 (project.edit)
* ``GET  /api/v1/projects/<id>/members``          (visibility of related list)
* ``POST /api/v1/projects/<id>/members``          (project.assign_members)
* ``POST /api/v1/projects/<id>/documents/link``   (docs.upload)
* ``POST /api/v1/tasks`` (with project_id)        (tasks.create)

Run::

    .\\.venv\\Scripts\\python.exe manage.py shell -c "exec(open('scripts/access_http_matrix_smoke.py', encoding='utf8').read())"
"""

from __future__ import annotations

import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from django.conf import settings as _dj_settings

if "testserver" not in (_dj_settings.ALLOWED_HOSTS or []):
    _dj_settings.ALLOWED_HOSTS = list(_dj_settings.ALLOWED_HOSTS or []) + ["testserver"]

from apps.access import service as access_service
from apps.access.models import PermissionGrant
from apps.identity.models import Role, UserRole
from apps.organizations.models import Organization, OrganizationMember
from apps.projects.models import Project, ProjectMember

User = get_user_model()
TAG = "http-matrix"


def _u(username: str, *, super_user: bool = False) -> User:
    user, _ = User.objects.get_or_create(
        username=username,
        defaults={"email": f"{username}@http-matrix.test", "is_active": True},
    )
    user.is_active = True
    user.is_staff = super_user
    user.is_superuser = super_user
    user.save()
    return user


def _purge(users: list[User], project: Project) -> None:
    PermissionGrant.objects.filter(employee__in=users, note__startswith=TAG).delete()
    ProjectMember.objects.filter(project=project, user__in=users).delete()


def _assert_status(client_label: str, label: str, response, allowed: tuple[int, ...]) -> None:
    code = response.status_code
    if code in allowed:
        print(f"    [OK] {client_label} {label}: {code} (expected {allowed})")
        return
    body = response.content.decode("utf-8", errors="ignore")[:240]
    print(f"    [FAIL] {client_label} {label}: {code} (expected {allowed}) body={body}")
    raise SystemExit(1)


def _post_json(client: Client, url: str, payload: dict):
    return client.post(url, data=json.dumps(payload), content_type="application/json")


def _patch_json(client: Client, url: str, payload: dict):
    return client.patch(url, data=json.dumps(payload), content_type="application/json")


def main() -> None:
    print("=== http access matrix smoke ===")

    super_user = _u("http-super", super_user=True)
    owner = _u("http-owner")
    viewer = _u("http-viewer")
    grant_only = _u("http-grant-only")
    stranger = _u("http-stranger")
    extra_member = _u("http-extra")  # candidate for member-add operations
    all_users = [super_user, owner, viewer, grant_only, stranger, extra_member]

    org, _ = Organization.objects.get_or_create(slug="http-org", defaults={"name": "HTTP Org"})
    project, _ = Project.objects.get_or_create(
        organization=org,
        name="HTTP Arena",
        defaults={"status": Project.STATUS_ACTIVE, "code": "http-arena"},
    )
    for u in all_users:
        OrganizationMember.objects.update_or_create(
            user=u, organization=org, defaults={"is_active": True}
        )

    super_role, _ = Role.objects.get_or_create(code="super_admin", defaults={"name": "Super Admin"})
    UserRole.objects.update_or_create(user=super_user, role=super_role, organization=None, defaults={})

    _purge(all_users, project)
    project.created_by = owner
    project.save(update_fields=["created_by"])
    ProjectMember.objects.update_or_create(
        project=project, user=owner, defaults={"role": ProjectMember.ROLE_OWNER, "is_active": True}
    )
    ProjectMember.objects.update_or_create(
        project=project, user=viewer, defaults={"role": ProjectMember.ROLE_VIEWER, "is_active": True}
    )

    grant_only_grant = access_service.grant_permission(
        employee=grant_only,
        permission_code="docs.upload",
        scope_type="project",
        scope_id=str(project.pk),
        granted_by=super_user,
        expires_at=timezone.now() + timedelta(days=14),
        note=f"{TAG}:grant-only",
    ).grant

    detail_url = f"/api/v1/projects/{project.pk}"
    members_url = f"/api/v1/projects/{project.pk}/members"
    docs_link_url = f"/api/v1/projects/{project.pk}/documents/link"
    tasks_url = "/api/v1/tasks"

    expectations = {
        "super": {
            "user": super_user,
            "GET detail": (200,),
            "PATCH detail": (200,),
            "GET members": (200,),
            "POST members": (200, 201),
            "POST docs.link": (200, 201),
            "POST tasks (own)": (201,),
        },
        "owner": {
            "user": owner,
            "GET detail": (200,),
            "PATCH detail": (200,),
            "GET members": (200,),
            "POST members": (200, 201),
            "POST docs.link": (200, 201),
            "POST tasks (own)": (201,),
        },
        "viewer": {
            "user": viewer,
            "GET detail": (200,),
            "PATCH detail": (403,),
            "GET members": (200,),
            "POST members": (403,),
            "POST docs.link": (403,),
            "POST tasks (own)": (403,),
        },
        "grant_only": {
            "user": grant_only,
            "GET detail": (200,),
            "PATCH detail": (403,),
            "GET members": (200,),
            "POST members": (403,),
            "POST docs.link": (200, 201),
            "POST tasks (own)": (403,),
        },
        "stranger": {
            "user": stranger,
            "GET detail": (403, 404),
            "PATCH detail": (403, 404),
            "GET members": (403, 404),
            "POST members": (403, 404),
            "POST docs.link": (403, 404),
            "POST tasks (own)": (403,),
        },
    }

    extra_member_id = extra_member.pk

    for label, spec in expectations.items():
        user = spec["user"]
        client = Client()
        client.force_login(user)

        print(f"-- archetype: {label} ({user.username}) --")
        # Fresh resource for member-add to avoid coupling between archetypes.
        ProjectMember.objects.filter(project=project, user=extra_member).delete()

        _assert_status(label, "GET detail", client.get(detail_url), spec["GET detail"])
        _assert_status(
            label,
            "PATCH detail",
            _patch_json(client, detail_url, {"description": f"updated by {label}"}),
            spec["PATCH detail"],
        )
        _assert_status(label, "GET members", client.get(members_url), spec["GET members"])
        _assert_status(
            label,
            "POST members",
            _post_json(
                client,
                members_url,
                {"user": extra_member_id, "role": ProjectMember.ROLE_EDITOR, "is_active": True},
            ),
            spec["POST members"],
        )
        _assert_status(
            label,
            "POST docs.link",
            _post_json(
                client,
                docs_link_url,
                {"title": f"http-link-{label}", "url": "https://example.com/spec.pdf"},
            ),
            spec["POST docs.link"],
        )
        _assert_status(
            label,
            "POST tasks (own)",
            _post_json(
                client,
                tasks_url,
                {
                    "title": f"task by {label}",
                    "project_id": project.pk,
                    # 11 — known mock assignee id (apps/core/api/parallel_contract_views.COMPANY_USERS)
                    "assignee_id": 11,
                    "priority": "medium",
                    "status": "todo",
                },
            ),
            spec["POST tasks (own)"],
        )

    print("[isolation] grant_only does NOT see another project")
    other_project, _ = Project.objects.get_or_create(
        organization=org,
        name="HTTP Olympus",
        defaults={"status": Project.STATUS_ACTIVE, "code": "http-olympus"},
    )
    isolation_client = Client()
    isolation_client.force_login(grant_only)
    resp = isolation_client.get(f"/api/v1/projects/{other_project.pk}")
    _assert_status("grant_only", "GET other project", resp, (403, 404))

    print("[debug] super requesting include=access_source on detail")
    super_client = Client()
    super_client.force_login(super_user)
    resp = super_client.get(f"{detail_url}?include=access_source")
    body = resp.json()
    assert resp.status_code == 200
    assert "access_source" in body and body["access_source"] is not None, body
    src = body["access_source"]
    assert "is_privileged_role" in src
    print("    [OK] access_source payload:", sorted(src.keys()))

    print("[cleanup]")
    access_service.revoke_permission(
        grant_only_grant, revoked_by=super_user, note=f"{TAG}:cleanup"
    )
    _purge(all_users, project)
    print("=== http access matrix smoke OK ===")


main()
