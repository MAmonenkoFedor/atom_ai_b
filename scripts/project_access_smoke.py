"""Smoke-check project-scoped grants against project capabilities.

Run:
    .\\.venv\\Scripts\\python.exe manage.py shell -c "exec(open('scripts/project_access_smoke.py', encoding='utf8').read())"
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

from apps.access import service as access_service
from apps.access.models import PermissionGrant
from apps.projects.api.serializers import ProjectSerializer
from apps.projects.list_annotations import projects_queryset_with_annotations
from apps.projects.models import Project, ProjectMember
from apps.projects.project_permissions import can_project_action, project_capabilities


User = get_user_model()


class _Req:
    def __init__(self, user):
        self.user = user


def main() -> None:
    actor = User.objects.filter(username="super_admin_test").first()
    target = User.objects.filter(username="employee_test").first()
    project = Project.objects.order_by("id").first()
    assert actor and target and project, "seed_test_credentials and project seed are required"

    PermissionGrant.objects.filter(employee=target, note__startswith="project-access-smoke").delete()
    ProjectMember.objects.filter(project=project, user=target).delete()

    print(f"project={project.id}:{project.name} target={target.username}")
    print("[1] no member and no grant -> cannot upload docs")
    assert not can_project_action(target, project, "docs.upload", legacy_manage=False)

    print("[2] grant docs.upload @ project")
    grant = access_service.grant_permission(
        employee=target,
        permission_code="docs.upload",
        scope_type="project",
        scope_id=str(project.id),
        grant_mode=PermissionGrant.GRANT_MODE_USE_ONLY,
        granted_by=actor,
        note="project-access-smoke",
    ).grant
    assert can_project_action(target, project, "docs.upload", legacy_manage=False)

    print("[3] granted project appears in visible queryset")
    assert projects_queryset_with_annotations(target).filter(pk=project.pk).exists()

    print("[4] serializer exposes functional flags")
    payload = ProjectSerializer(project, context={"request": _Req(target)}).data
    assert payload["capabilities"]["can_upload_documents"] is True, payload["capabilities"]
    assert project_capabilities(target, project)["can_upload_documents"] is True

    print("[5] cleanup")
    access_service.revoke_permission(grant, revoked_by=actor, note="project-access-smoke-cleanup")
    print("=== project access smoke OK ===")


main()
