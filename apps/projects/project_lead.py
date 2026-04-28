"""Назначение руководителя проекта и пакетных project-scoped прав (как у отделов)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.access.models import PermissionGrant, SCOPE_PROJECT
from apps.access.service import UnknownPermission, grant_permission, revoke_permission
from apps.audit.service import emit_audit_event
from apps.organizations.models import OrganizationMember
from apps.projects.lead_payload import project_lead_scoped_note
from apps.projects.models import Project, ProjectMember

User = get_user_model()


def _grant_project_permission_with_fallback(
    *,
    employee,
    primary_code: str,
    fallback_codes: list[str],
    scope_id: int,
    grant_mode: str,
    granted_by,
    note: str,
    request,
) -> None:
    """
    Grant project-scoped permission resiliently:
    - first, try the canonical project.* code;
    - if it is not present in PermissionDefinition, fallback to legacy aliases.
    """
    codes = [primary_code, *fallback_codes]
    last_error: UnknownPermission | None = None
    for code in codes:
        try:
            grant_permission(
                employee=employee,
                permission_code=code,
                scope_type=SCOPE_PROJECT,
                scope_id=str(scope_id),
                grant_mode=grant_mode,
                granted_by=granted_by,
                note=note,
                request=request,
            )
            return
        except UnknownPermission as exc:
            last_error = exc
            continue
    raise ValidationError(
        {
            "detail": (
                f"В каталоге прав нет permission definition для {primary_code} "
                "(и fallback-кодов). Выполните seed_access_control."
            )
        }
    ) from last_error


def revoke_project_lead_scoped_grants(*, employee, project_id: int, revoked_by, request) -> int:
    n = 0
    note = project_lead_scoped_note(project_id)
    qs = PermissionGrant.objects.filter(
        employee=employee,
        status=PermissionGrant.STATUS_ACTIVE,
        scope_type=SCOPE_PROJECT,
        scope_id=str(project_id),
        note=note,
    )
    for g in list(qs):
        revoke_permission(
            g,
            revoked_by=revoked_by,
            note="project_lead_scoped_revoke",
            request=request,
        )
        n += 1
    return n


def can_assign_project_lead(actor, project: Project) -> bool:
    """Владелец/менеджер проекта, company/super admin по организации проекта."""
    if not actor or not getattr(actor, "is_authenticated", False):
        return False
    from apps.core.api.permissions import normalized_roles_for_user
    from apps.projects.project_permissions import can_manage_project

    if can_manage_project(actor, project):
        return True
    roles = normalized_roles_for_user(actor)
    if "super_admin" in roles:
        return True
    if "company_admin" in roles:
        return OrganizationMember.objects.filter(
            user=actor, organization_id=project.organization_id, is_active=True
        ).exists()
    return False


def _assert_can_assign(actor, project: Project) -> None:
    if not can_assign_project_lead(actor, project):
        raise PermissionDenied("Нет права назначать руководителя проекта.")


@transaction.atomic
def assign_project_lead(
    *,
    request,
    project: Project,
    user,
    grant_project_edit: bool,
    grant_project_assign_members: bool,
    grant_project_docs_view: bool = False,
    grant_project_docs_upload: bool = False,
    grant_project_docs_edit: bool = False,
    grant_project_docs_assign_editors: bool = False,
    grant_project_tasks_view: bool = False,
    grant_project_tasks_create: bool = False,
    grant_project_tasks_assign: bool = False,
    grant_project_tasks_change_deadline: bool = False,
) -> Project:
    _assert_can_assign(request.user, project)
    if not OrganizationMember.objects.filter(
        user=user, organization_id=project.organization_id, is_active=True
    ).exists():
        raise ValidationError({"user_id": "Пользователь не состоит в организации этого проекта."})

    prev_leads = list(
        ProjectMember.objects.filter(project=project, is_lead=True).select_related("user")
    )
    for m in prev_leads:
        if m.user_id == user.id:
            continue
        if m.user:
            revoke_project_lead_scoped_grants(
                employee=m.user,
                project_id=project.id,
                revoked_by=request.user,
                request=request,
            )
        m.is_lead = False
        upd = ["is_lead"]
        if m.role == ProjectMember.ROLE_LEAD:
            m.role = ProjectMember.ROLE_EDITOR
            upd.append("role")
        m.save(update_fields=upd)

    member, created = ProjectMember.objects.get_or_create(
        project=project,
        user=user,
        defaults={
            "role": ProjectMember.ROLE_EDITOR,
            "is_active": True,
            "is_lead": True,
            "assigned_by": request.user,
        },
    )
    if not created:
        member.is_active = True
        member.is_lead = True
        member.assigned_by = request.user
        member.save(update_fields=["is_active", "is_lead", "assigned_by"])

    revoke_project_lead_scoped_grants(
        employee=user,
        project_id=project.id,
        revoked_by=request.user,
        request=request,
    )
    note = project_lead_scoped_note(project.id)
    mode = PermissionGrant.GRANT_MODE_USE_AND_DELEGATE
    if grant_project_edit:
        _grant_project_permission_with_fallback(
            employee=user,
            primary_code="project.edit",
            fallback_codes=[],
            scope_id=project.id,
            grant_mode=mode,
            granted_by=request.user,
            note=note,
            request=request,
        )
    if grant_project_assign_members:
        _grant_project_permission_with_fallback(
            employee=user,
            primary_code="project.assign_members",
            fallback_codes=[],
            scope_id=project.id,
            grant_mode=mode,
            granted_by=request.user,
            note=note,
            request=request,
        )
    if grant_project_docs_view:
        _grant_project_permission_with_fallback(
            employee=user,
            primary_code="project.docs.view",
            fallback_codes=["docs.view"],
            scope_id=project.id,
            grant_mode=mode,
            granted_by=request.user,
            note=note,
            request=request,
        )
    if grant_project_docs_upload:
        _grant_project_permission_with_fallback(
            employee=user,
            primary_code="project.docs.upload",
            fallback_codes=["docs.upload"],
            scope_id=project.id,
            grant_mode=mode,
            granted_by=request.user,
            note=note,
            request=request,
        )
    if grant_project_docs_edit:
        _grant_project_permission_with_fallback(
            employee=user,
            primary_code="project.docs.edit",
            fallback_codes=["docs.edit"],
            scope_id=project.id,
            grant_mode=mode,
            granted_by=request.user,
            note=note,
            request=request,
        )
    if grant_project_docs_assign_editors:
        _grant_project_permission_with_fallback(
            employee=user,
            primary_code="project.docs.assign_editors",
            fallback_codes=["docs.assign_editors"],
            scope_id=project.id,
            grant_mode=mode,
            granted_by=request.user,
            note=note,
            request=request,
        )
    if grant_project_tasks_view:
        _grant_project_permission_with_fallback(
            employee=user,
            primary_code="project.tasks.view",
            fallback_codes=["tasks.view"],
            scope_id=project.id,
            grant_mode=mode,
            granted_by=request.user,
            note=note,
            request=request,
        )
    if grant_project_tasks_create:
        _grant_project_permission_with_fallback(
            employee=user,
            primary_code="project.tasks.create",
            fallback_codes=["tasks.create"],
            scope_id=project.id,
            grant_mode=mode,
            granted_by=request.user,
            note=note,
            request=request,
        )
    if grant_project_tasks_assign:
        _grant_project_permission_with_fallback(
            employee=user,
            primary_code="project.tasks.assign",
            fallback_codes=["tasks.assign"],
            scope_id=project.id,
            grant_mode=mode,
            granted_by=request.user,
            note=note,
            request=request,
        )
    if grant_project_tasks_change_deadline:
        _grant_project_permission_with_fallback(
            employee=user,
            primary_code="project.tasks.change_deadline",
            fallback_codes=["tasks.change_deadline"],
            scope_id=project.id,
            grant_mode=mode,
            granted_by=request.user,
            note=note,
            request=request,
        )

    try:
        emit_audit_event(
            request,
            event_type="project.project_lead_set",
            action="set_lead",
            entity_type="project",
            entity_id=str(project.id),
            project_id=str(project.id),
            payload={
                "project_id": project.id,
                "organization_id": project.organization_id,
                "user_id": user.id,
                "grant_project_edit": grant_project_edit,
                "grant_project_assign_members": grant_project_assign_members,
                "grant_project_docs_view": grant_project_docs_view,
                "grant_project_docs_upload": grant_project_docs_upload,
                "grant_project_docs_edit": grant_project_docs_edit,
                "grant_project_docs_assign_editors": grant_project_docs_assign_editors,
                "grant_project_tasks_view": grant_project_tasks_view,
                "grant_project_tasks_create": grant_project_tasks_create,
                "grant_project_tasks_assign": grant_project_tasks_assign,
                "grant_project_tasks_change_deadline": grant_project_tasks_change_deadline,
            },
        )
    except Exception:
        pass
    return project


@transaction.atomic
def clear_project_lead(*, request, project: Project) -> Project:
    _assert_can_assign(request.user, project)
    m = (
        ProjectMember.objects.filter(project=project, is_lead=True, is_active=True)
        .select_related("user")
        .first()
    )
    if not m or not m.user_id:
        raise ValidationError({"detail": "Назначенного руководителя проекта нет."})
    u = m.user
    revoke_project_lead_scoped_grants(
        employee=u,
        project_id=project.id,
        revoked_by=request.user,
        request=request,
    )
    m.is_lead = False
    upd = ["is_lead"]
    if m.role == ProjectMember.ROLE_LEAD:
        m.role = ProjectMember.ROLE_EDITOR
        upd.append("role")
    m.save(update_fields=upd)
    try:
        emit_audit_event(
            request,
            event_type="project.project_lead_cleared",
            action="clear_lead",
            entity_type="project",
            entity_id=str(project.id),
            project_id=str(project.id),
            payload={
                "project_id": project.id,
                "organization_id": project.organization_id,
                "user_id": u.id,
            },
        )
    except Exception:
        pass
    return project


def get_project_for_lead_endpoint(request, project_id: int) -> Project:
    from apps.projects.list_annotations import projects_queryset_with_annotations

    return get_object_or_404(projects_queryset_with_annotations(request.user), pk=project_id)
