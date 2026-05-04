"""Policy helpers layered on top of access grants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from apps.access import resolver as access_resolver


@dataclass(frozen=True)
class AiWorkspaceAccessDecision:
    can_view_metadata: bool
    can_view_content: bool
    reason: str


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    access_level: Literal["none", "metadata", "read", "write", "manage", "admin"]
    reason: str
    scope_type: str
    scope_id: str | None
    subject_id: int
    object_id: int | None


def policy_audit_payload(decision: PolicyDecision) -> dict[str, str]:
    """Stable fields for audit rows on sensitive project/resource actions."""
    return {
        "access_level": decision.access_level,
        "reason": decision.reason,
        "scope_type": decision.scope_type,
        "scope_id": decision.scope_id or "",
    }


def _subject_id(viewer) -> int:
    return int(getattr(viewer, "id", 0) or 0)


def _resolve_ai_workspace_decision(*, viewer, owner_user_id: int) -> PolicyDecision:
    subject_id = _subject_id(viewer)
    scope_id = str(owner_user_id)
    if not viewer or not getattr(viewer, "is_authenticated", False):
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason="anonymous",
            scope_type="ai_workspace",
            scope_id=scope_id,
            subject_id=subject_id,
            object_id=owner_user_id,
        )

    if subject_id == int(owner_user_id):
        return PolicyDecision(
            allowed=True,
            access_level="read",
            reason="self",
            scope_type="ai_workspace",
            scope_id=scope_id,
            subject_id=subject_id,
            object_id=owner_user_id,
        )

    if bool(getattr(viewer, "is_superuser", False)):
        return PolicyDecision(
            allowed=True,
            access_level="admin",
            reason="superuser",
            scope_type="ai_workspace",
            scope_id=scope_id,
            subject_id=subject_id,
            object_id=owner_user_id,
        )

    can_view_content = access_resolver.has_permission(
        viewer,
        "ai.workspace.view_content",
        scope_type="ai_workspace",
        scope_id=scope_id,
    )
    if can_view_content:
        return PolicyDecision(
            allowed=True,
            access_level="read",
            reason="permission:ai.workspace.view_content",
            scope_type="ai_workspace",
            scope_id=scope_id,
            subject_id=subject_id,
            object_id=owner_user_id,
        )

    can_view_metadata = access_resolver.has_permission(
        viewer,
        "ai.workspace.view_metadata",
        scope_type="ai_workspace",
        scope_id=scope_id,
    )
    if can_view_metadata:
        return PolicyDecision(
            allowed=True,
            access_level="metadata",
            reason="permission:ai.workspace.view_metadata",
            scope_type="ai_workspace",
            scope_id=scope_id,
            subject_id=subject_id,
            object_id=owner_user_id,
        )

    return PolicyDecision(
        allowed=False,
        access_level="none",
        reason="no_permission",
        scope_type="ai_workspace",
        scope_id=scope_id,
        subject_id=subject_id,
        object_id=owner_user_id,
    )


def _coerce_project_resource(*, resource, scope_id: str | None):
    from apps.projects.models import Project

    if isinstance(resource, Project):
        return resource
    if scope_id is None:
        return None
    try:
        pk = int(str(scope_id))
    except (TypeError, ValueError):
        return None
    return Project.objects.filter(pk=pk).first()


def _resolve_project_create(*, user, resource) -> PolicyDecision:
    from apps.organizations.models import Organization, OrganizationMember

    subject_id = _subject_id(user)
    if not user or not getattr(user, "is_authenticated", False):
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason="anonymous",
            scope_type="project",
            scope_id=None,
            subject_id=subject_id,
            object_id=None,
        )
    if not isinstance(resource, Organization):
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason="invalid_resource",
            scope_type="project",
            scope_id=None,
            subject_id=subject_id,
            object_id=None,
        )
    org = resource
    sid = str(org.pk)
    if not OrganizationMember.objects.filter(user=user, organization=org, is_active=True).exists():
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason="not_organization_member",
            scope_type="project",
            scope_id=sid,
            subject_id=subject_id,
            object_id=None,
        )
    if bool(getattr(user, "is_superuser", False)):
        return PolicyDecision(
            allowed=True,
            access_level="admin",
            reason="superuser",
            scope_type="project",
            scope_id=sid,
            subject_id=subject_id,
            object_id=None,
        )
    if access_resolver.has_permission(
        user,
        "project.create",
        scope_type="company",
        scope_id=sid,
    ):
        return PolicyDecision(
            allowed=True,
            access_level="write",
            reason="permission:project.create",
            scope_type="project",
            scope_id=sid,
            subject_id=subject_id,
            object_id=None,
        )
    return PolicyDecision(
        allowed=False,
        access_level="none",
        reason="requires:project.create",
        scope_type="project",
        scope_id=sid,
        subject_id=subject_id,
        object_id=None,
    )


def _resolve_project_action(*, user, action: str, project) -> PolicyDecision:
    from apps.projects.project_permissions import compute_project_policy_decision, has_project_access_permission

    base = compute_project_policy_decision(user, project)
    subject_id = base.subject_id
    scope_sid = base.scope_id
    object_id = base.object_id

    action_min_levels: dict[str, frozenset[str]] = {
        "project.view_metadata": frozenset({"metadata", "read", "write", "manage", "admin"}),
        "project.read": frozenset({"read", "write", "manage", "admin"}),
        "project.update": frozenset({"write", "manage", "admin"}),
        "project.archive": frozenset({"write", "manage", "admin"}),
        "project.manage_members": frozenset({"manage", "admin"}),
        # Primary org unit / governance-style fields use this action (stricter than project.update).
        "project.manage_settings": frozenset({"manage", "admin"}),
    }

    if action == "project.delete":
        allowed = base.access_level in {"manage", "admin"} or has_project_access_permission(
            user, project, "project.delete"
        )
        reason = base.reason if allowed else "requires:project.delete"
        return PolicyDecision(
            allowed=allowed,
            access_level=base.access_level if allowed else "none",
            reason=reason,
            scope_type="project",
            scope_id=scope_sid,
            subject_id=subject_id,
            object_id=object_id,
        )

    allowed_levels = action_min_levels.get(action)
    if allowed_levels is None:
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason="unsupported_action",
            scope_type="project",
            scope_id=scope_sid,
            subject_id=subject_id,
            object_id=object_id,
        )
    if base.access_level in allowed_levels:
        return PolicyDecision(
            allowed=True,
            access_level=base.access_level,
            reason=base.reason,
            scope_type="project",
            scope_id=scope_sid,
            subject_id=subject_id,
            object_id=object_id,
        )
    return PolicyDecision(
        allowed=False,
        access_level="none",
        reason=f"requires:{action}",
        scope_type="project",
        scope_id=scope_sid,
        subject_id=subject_id,
        object_id=object_id,
    )


def _coerce_department_resource(*, resource, scope_id: str | None):
    from apps.orgstructure.models import OrgUnit

    if isinstance(resource, OrgUnit):
        return resource
    if scope_id is None:
        return None
    try:
        pk = int(str(scope_id))
    except (TypeError, ValueError):
        return None
    return OrgUnit.objects.filter(pk=pk).first()


def _resolve_department_action(*, user, action: str, org_unit) -> PolicyDecision:
    from apps.orgstructure.department_permissions import compute_department_policy_decision

    base = compute_department_policy_decision(user, org_unit)
    subject_id = base.subject_id
    scope_sid = base.scope_id
    object_id = base.object_id

    action_min_levels: dict[str, frozenset[str]] = {
        "department.view_metadata": frozenset({"metadata", "read", "write", "manage", "admin"}),
        "department.read": frozenset({"read", "write", "manage", "admin"}),
        "department.update": frozenset({"write", "manage", "admin"}),
        "department.manage_members": frozenset({"manage", "admin"}),
        "department.manage_workspace": frozenset({"manage", "admin"}),
        "department.manage_documents": frozenset({"write", "manage", "admin"}),
        "department.view_reports": frozenset({"read", "write", "manage", "admin"}),
        "department.use_ai": frozenset({"read", "write", "manage", "admin"}),
    }

    if not base.allowed:
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason=base.reason,
            scope_type="department",
            scope_id=scope_sid,
            subject_id=subject_id,
            object_id=object_id,
        )

    allowed_levels = action_min_levels.get(action)
    if allowed_levels is None:
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason="unsupported_action",
            scope_type="department",
            scope_id=scope_sid,
            subject_id=subject_id,
            object_id=object_id,
        )
    if base.access_level in allowed_levels:
        return PolicyDecision(
            allowed=True,
            access_level=base.access_level,
            reason=base.reason,
            scope_type="department",
            scope_id=scope_sid,
            subject_id=subject_id,
            object_id=object_id,
        )
    return PolicyDecision(
        allowed=False,
        access_level="none",
        reason=f"requires:{action}",
        scope_type="department",
        scope_id=scope_sid,
        subject_id=subject_id,
        object_id=object_id,
    )


def _coerce_employee_resource(*, resource, scope_id: str | None):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    if isinstance(resource, User):
        return resource
    if scope_id is None:
        return None
    try:
        pk = int(str(scope_id))
    except (TypeError, ValueError):
        return None
    return User.objects.filter(pk=pk).first()


def _resolve_employee_action(*, user, action: str, employee) -> PolicyDecision:
    from apps.orgstructure.employee_permissions import (
        compute_employee_policy_decision,
        has_employee_scoped_permission,
    )

    base = compute_employee_policy_decision(user, employee)
    subject_id = base.subject_id
    scope_sid = base.scope_id
    object_id = base.object_id

    # Workspace visibility can be delegated independently of profile read.
    if action in {"employee.view_workspace_metadata", "employee.view_workspace_content"}:
        wants_content = action == "employee.view_workspace_content"
        if base.access_level in {"read", "write", "manage", "admin"}:
            return PolicyDecision(
                allowed=True,
                access_level=base.access_level,
                reason=base.reason,
                scope_type="employee",
                scope_id=scope_sid,
                subject_id=subject_id,
                object_id=object_id,
            )
        workspace_code = (
            "employee.view_workspace_content"
            if wants_content
            else "employee.view_workspace_metadata"
        )
        if has_employee_scoped_permission(user, employee, workspace_code):
            return PolicyDecision(
                allowed=True,
                access_level=("read" if wants_content else "metadata"),
                reason=f"permission:{workspace_code}",
                scope_type="employee",
                scope_id=scope_sid,
                subject_id=subject_id,
                object_id=object_id,
            )
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason=f"requires:{workspace_code}",
            scope_type="employee",
            scope_id=scope_sid,
            subject_id=subject_id,
            object_id=object_id,
        )

    action_min_levels: dict[str, frozenset[str]] = {
        "employee.view_metadata": frozenset({"metadata", "read", "write", "manage", "admin"}),
        "employee.read": frozenset({"read", "write", "manage", "admin"}),
        "employee.update": frozenset({"write", "manage", "admin"}),
        "employee.manage_roles": frozenset({"manage", "admin"}),
    }
    allowed_levels = action_min_levels.get(action)
    if allowed_levels is None:
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason="unsupported_action",
            scope_type="employee",
            scope_id=scope_sid,
            subject_id=subject_id,
            object_id=object_id,
        )
    if base.access_level in allowed_levels:
        return PolicyDecision(
            allowed=True,
            access_level=base.access_level,
            reason=base.reason,
            scope_type="employee",
            scope_id=scope_sid,
            subject_id=subject_id,
            object_id=object_id,
        )
    return PolicyDecision(
        allowed=False,
        access_level="none",
        reason=f"requires:{action}",
        scope_type="employee",
        scope_id=scope_sid,
        subject_id=subject_id,
        object_id=object_id,
    )


def _resolve_task_access(*, user, action: str, scope_id: str | None, resource) -> PolicyDecision:
    from apps.projects.project_permissions import (
        can_assign_project_tasks,
        can_block_project_tasks,
        can_project_task_action,
    )
    from apps.workspaces.task_policy import (
        compute_workspace_task_policy_decision,
        normalize_workspace_task_resource,
        resolve_workspace_task_project,
    )

    employee_id, task = normalize_workspace_task_resource(resource, scope_id)
    subject_id = _subject_id(user)
    sid = str(scope_id or "").strip() or (f"bucket:{employee_id}" if employee_id else "")

    if not employee_id:
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason="invalid_task_resource",
            scope_type="task",
            scope_id=sid,
            subject_id=subject_id,
            object_id=None,
        )

    base = compute_workspace_task_policy_decision(user=user, employee_id=employee_id, task=task)
    scope_sid = base.scope_id
    project = resolve_workspace_task_project(task)

    if project is not None:
        if action == "task.assign" and can_assign_project_tasks(user, project):
            return PolicyDecision(
                allowed=True,
                access_level=base.access_level,
                reason="permission:tasks.assign",
                scope_type="task",
                scope_id=scope_sid,
                subject_id=base.subject_id,
                object_id=None,
            )
        if action == "task.block" and can_block_project_tasks(user, project):
            if base.access_level in {"read", "write", "manage", "admin"}:
                return PolicyDecision(
                    allowed=True,
                    access_level=base.access_level,
                    reason="permission:tasks.block",
                    scope_type="task",
                    scope_id=scope_sid,
                    subject_id=base.subject_id,
                    object_id=None,
                )
        if action == "task.escalate" and can_project_task_action(
            user, project, "tasks.assign", legacy_manage=True
        ):
            if base.access_level in {"read", "write", "manage", "admin"}:
                return PolicyDecision(
                    allowed=True,
                    access_level=base.access_level,
                    reason="permission:tasks.assign",
                    scope_type="task",
                    scope_id=scope_sid,
                    subject_id=base.subject_id,
                    object_id=None,
                )

    action_min: dict[str, frozenset[str]] = {
        "task.view_metadata": frozenset({"metadata", "read", "write", "manage", "admin"}),
        "task.read": frozenset({"read", "write", "manage", "admin"}),
        "task.create": frozenset({"write", "manage", "admin"}),
        "task.update": frozenset({"write", "manage", "admin"}),
        "task.assign": frozenset({"manage", "admin"}),
        "task.change_status": frozenset({"write", "manage", "admin"}),
        "task.comment": frozenset({"read", "write", "manage", "admin"}),
        "task.upload_artifact": frozenset({"write", "manage", "admin"}),
        "task.review": frozenset({"read", "write", "manage", "admin"}),
        "task.block": frozenset({"write", "manage", "admin"}),
        "task.escalate": frozenset({"manage", "admin"}),
        "task.delete": frozenset({"write", "manage", "admin"}),
    }
    allowed_levels = action_min.get(action)
    if allowed_levels is None:
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason="unsupported_action",
            scope_type="task",
            scope_id=scope_sid,
            subject_id=base.subject_id,
            object_id=None,
        )
    if base.access_level in allowed_levels:
        return PolicyDecision(
            allowed=True,
            access_level=base.access_level,
            reason=base.reason,
            scope_type="task",
            scope_id=scope_sid,
            subject_id=base.subject_id,
            object_id=None,
        )
    return PolicyDecision(
        allowed=False,
        access_level="none",
        reason=f"requires:{action}",
        scope_type="task",
        scope_id=scope_sid,
        subject_id=base.subject_id,
        object_id=None,
    )


def resolve_access(
    *,
    user,
    action: str,
    scope_type: str,
    scope_id: str | None = None,
    resource=None,
) -> PolicyDecision:
    """Resolve access decision in a uniform contract.

    Supported ``scope_type`` values include ``ai_workspace``, ``document``,
    ``project``, ``department`` (OrgUnit / department workspace), ``employee``,
    and ``task`` (workspace employee-vertical tasks; see
    ``_resolve_task_access``).
    """

    if scope_type == "ai_workspace" and scope_id:
        try:
            owner_user_id = int(str(scope_id))
        except ValueError:
            return PolicyDecision(
                allowed=False,
                access_level="none",
                reason="invalid_scope_id",
                scope_type=scope_type,
                scope_id=scope_id,
                subject_id=_subject_id(user),
                object_id=None,
            )
        base = _resolve_ai_workspace_decision(viewer=user, owner_user_id=owner_user_id)
        if action == "ai.workspace.view_content":
            allowed = base.access_level in {"read", "write", "manage", "admin"}
            reason = base.reason if allowed else "requires:ai.workspace.view_content"
            return PolicyDecision(
                allowed=allowed,
                access_level=base.access_level if allowed else "none",
                reason=reason,
                scope_type=base.scope_type,
                scope_id=base.scope_id,
                subject_id=base.subject_id,
                object_id=base.object_id,
            )
        if action == "ai.workspace.view_metadata":
            allowed = base.access_level in {"metadata", "read", "write", "manage", "admin"}
            reason = base.reason if allowed else "requires:ai.workspace.view_metadata"
            access_level = base.access_level if allowed else "none"
            return PolicyDecision(
                allowed=allowed,
                access_level=access_level,
                reason=reason,
                scope_type=base.scope_type,
                scope_id=base.scope_id,
                subject_id=base.subject_id,
                object_id=base.object_id,
            )

    if scope_type == "document":
        return _resolve_document_access(
            user=user,
            action=action,
            scope_id=scope_id,
            resource=resource,
        )

    if scope_type == "project":
        if action == "project.create":
            return _resolve_project_create(user=user, resource=resource)
        project = _coerce_project_resource(resource=resource, scope_id=scope_id)
        if project is None:
            return PolicyDecision(
                allowed=False,
                access_level="none",
                reason="invalid_project",
                scope_type="project",
                scope_id=scope_id,
                subject_id=_subject_id(user),
                object_id=None,
            )
        return _resolve_project_action(user=user, action=action, project=project)

    if scope_type == "task":
        return _resolve_task_access(user=user, action=action, scope_id=scope_id, resource=resource)

    if scope_type == "department":
        org_unit = _coerce_department_resource(resource=resource, scope_id=scope_id)
        if org_unit is None:
            return PolicyDecision(
                allowed=False,
                access_level="none",
                reason="invalid_department",
                scope_type="department",
                scope_id=scope_id,
                subject_id=_subject_id(user),
                object_id=None,
            )
        return _resolve_department_action(user=user, action=action, org_unit=org_unit)

    if scope_type == "employee":
        employee = _coerce_employee_resource(resource=resource, scope_id=scope_id)
        if employee is None:
            return PolicyDecision(
                allowed=False,
                access_level="none",
                reason="invalid_employee",
                scope_type="employee",
                scope_id=scope_id,
                subject_id=_subject_id(user),
                object_id=None,
            )
        return _resolve_employee_action(user=user, action=action, employee=employee)

    return PolicyDecision(
        allowed=False,
        access_level="none",
        reason="unsupported_policy_target",
        scope_type=scope_type,
        scope_id=scope_id,
        subject_id=_subject_id(user),
        object_id=None,
    )


def _resolve_department_document_base(*, user, org_unit, object_id: int | None) -> PolicyDecision:
    """Base document access when the backing resource is an :class:`~apps.orgstructure.models.OrgUnit`."""

    from apps.orgstructure.department_permissions import get_department_membership, has_department_access_permission

    subject_id = _subject_id(user)
    sid = str(org_unit.pk)
    oid = object_id

    if not user or not getattr(user, "is_authenticated", False):
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason="anonymous",
            scope_type="document",
            scope_id=sid,
            subject_id=subject_id,
            object_id=oid,
        )

    if has_department_access_permission(user, org_unit, "department.manage_documents"):
        return PolicyDecision(
            allowed=True,
            access_level="write",
            reason="permission:department.manage_documents",
            scope_type="document",
            scope_id=sid,
            subject_id=subject_id,
            object_id=oid,
        )

    if access_resolver.has_permission(
        user,
        "document.upload",
        scope_type="department",
        scope_id=sid,
    ):
        return PolicyDecision(
            allowed=True,
            access_level="write",
            reason="permission:document.upload",
            scope_type="document",
            scope_id=sid,
            subject_id=subject_id,
            object_id=oid,
        )

    if access_resolver.has_permission(
        user,
        "document.read",
        scope_type="department",
        scope_id=sid,
    ) or access_resolver.has_permission(
        user,
        "docs.view",
        scope_type="department",
        scope_id=sid,
    ):
        return PolicyDecision(
            allowed=True,
            access_level="read",
            reason="permission:document.read",
            scope_type="document",
            scope_id=sid,
            subject_id=subject_id,
            object_id=oid,
        )

    if get_department_membership(user, org_unit) is not None:
        return PolicyDecision(
            allowed=True,
            access_level="read",
            reason="department_membership",
            scope_type="document",
            scope_id=sid,
            subject_id=subject_id,
            object_id=oid,
        )

    if access_resolver.has_permission(
        user,
        "document.view_metadata",
        scope_type="department",
        scope_id=sid,
    ):
        return PolicyDecision(
            allowed=True,
            access_level="metadata",
            reason="permission:document.view_metadata",
            scope_type="document",
            scope_id=sid,
            subject_id=subject_id,
            object_id=oid,
        )

    return PolicyDecision(
        allowed=False,
        access_level="none",
        reason="no_permission",
        scope_type="document",
        scope_id=sid,
        subject_id=subject_id,
        object_id=oid,
    )


def _normalize_document_resource(resource, scope_id: str | None):
    """Normalize supported document resources.

    Returns tuple:
    ``(project, workspace_doc_owner_user_id, org_unit, object_id, scope_id_fallback)``
    """

    if resource is None:
        return None, None, None, None, scope_id

    # Lazy imports to avoid broad module coupling at import time.
    from apps.orgstructure.models import OrgUnit, OrgUnitDocument
    from apps.projects.models import Project, ProjectDocument
    from apps.workspaces.models import WorkspaceCabinetDocument

    if isinstance(resource, OrgUnitDocument):
        ou = resource.org_unit
        return None, None, ou, int(resource.id), str(ou.pk)
    if isinstance(resource, OrgUnit):
        return None, None, resource, None, str(resource.pk)
    if isinstance(resource, Project):
        return resource, None, None, int(resource.id), str(resource.id)
    if isinstance(resource, ProjectDocument):
        return resource.project, None, None, int(resource.id), str(resource.project_id)
    if isinstance(resource, WorkspaceCabinetDocument):
        return None, int(resource.user_id), None, int(resource.id), str(resource.user_id)
    if hasattr(resource, "user_id"):
        raw_user_id = getattr(resource, "user_id", None)
        try:
            owner_user_id = int(raw_user_id)
        except (TypeError, ValueError):
            owner_user_id = None
        if owner_user_id is not None:
            raw_obj_id = getattr(resource, "id", None)
            try:
                object_id = int(raw_obj_id) if raw_obj_id is not None else None
            except (TypeError, ValueError):
                object_id = None
            return None, owner_user_id, None, object_id, str(owner_user_id)

    return None, None, None, None, scope_id


def _resolve_document_base_decision(*, user, scope_id: str | None, resource) -> PolicyDecision:
    subject_id = _subject_id(user)
    if not user or not getattr(user, "is_authenticated", False):
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason="anonymous",
            scope_type="document",
            scope_id=scope_id,
            subject_id=subject_id,
            object_id=None,
        )

    project, workspace_owner_user_id, org_unit, object_id, normalized_scope_id = _normalize_document_resource(
        resource, scope_id
    )

    if org_unit is not None:
        return _resolve_department_document_base(user=user, org_unit=org_unit, object_id=object_id)

    if project is not None:
        from apps.projects.project_permissions import can_upload_project_docs, can_view_project_docs

        if can_upload_project_docs(user, project):
            return PolicyDecision(
                allowed=True,
                access_level="write",
                reason="permission:project.docs.upload",
                scope_type="document",
                scope_id=normalized_scope_id,
                subject_id=subject_id,
                object_id=object_id,
            )
        if can_view_project_docs(user, project):
            return PolicyDecision(
                allowed=True,
                access_level="read",
                reason="permission:project.docs.view",
                scope_type="document",
                scope_id=normalized_scope_id,
                subject_id=subject_id,
                object_id=object_id,
            )
        can_view_metadata = access_resolver.has_permission(
            user,
            "document.view_metadata",
            scope_type="project",
            scope_id=str(project.id),
        )
        if can_view_metadata:
            return PolicyDecision(
                allowed=True,
                access_level="metadata",
                reason="permission:document.view_metadata",
                scope_type="document",
                scope_id=normalized_scope_id,
                subject_id=subject_id,
                object_id=object_id,
            )
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason="no_permission",
            scope_type="document",
            scope_id=normalized_scope_id,
            subject_id=subject_id,
            object_id=object_id,
        )

    if workspace_owner_user_id is not None:
        base = _resolve_ai_workspace_decision(viewer=user, owner_user_id=workspace_owner_user_id)
        # Owner/superuser/content grants provide read-level content, metadata grants are metadata-only.
        access_level = "none"
        if base.access_level in {"read", "write", "manage", "admin"}:
            access_level = "read"
        elif base.access_level == "metadata":
            access_level = "metadata"
        return PolicyDecision(
            allowed=access_level != "none",
            access_level=access_level,  # type: ignore[arg-type]
            reason=base.reason,
            scope_type="document",
            scope_id=normalized_scope_id,
            subject_id=subject_id,
            object_id=object_id,
        )

    return PolicyDecision(
        allowed=False,
        access_level="none",
        reason="unsupported_document_resource",
        scope_type="document",
        scope_id=scope_id,
        subject_id=subject_id,
        object_id=object_id,
    )


def _resolve_document_access(*, user, action: str, scope_id: str | None, resource) -> PolicyDecision:
    base = _resolve_document_base_decision(user=user, scope_id=scope_id, resource=resource)

    action_requirements: dict[str, set[str]] = {
        "document.view_metadata": {"metadata", "read", "write", "manage", "admin"},
        "document.read": {"read", "write", "manage", "admin"},
        "document.upload": {"write", "manage", "admin"},
        "document.update": {"write", "manage", "admin"},
        "document.delete": {"write", "manage", "admin"},
        "document.share": {"write", "manage", "admin"},
    }
    allowed_levels = action_requirements.get(action)
    if allowed_levels is None:
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason="unsupported_action",
            scope_type="document",
            scope_id=base.scope_id,
            subject_id=base.subject_id,
            object_id=base.object_id,
        )
    if base.access_level in allowed_levels:
        return PolicyDecision(
            allowed=True,
            access_level=base.access_level,
            reason=base.reason,
            scope_type=base.scope_type,
            scope_id=base.scope_id,
            subject_id=base.subject_id,
            object_id=base.object_id,
        )
    return PolicyDecision(
        allowed=False,
        access_level="none",
        reason=f"requires:{action}",
        scope_type=base.scope_type,
        scope_id=base.scope_id,
        subject_id=base.subject_id,
        object_id=base.object_id,
    )


def resolve_ai_workspace_access(*, viewer, owner_user_id: int) -> AiWorkspaceAccessDecision:
    """Compatibility adapter for existing AI workspace callers."""

    decision = _resolve_ai_workspace_decision(viewer=viewer, owner_user_id=owner_user_id)
    can_view_content = decision.access_level in {"read", "write", "manage", "admin"}
    can_view_metadata = decision.access_level in {"metadata", "read", "write", "manage", "admin"}
    return AiWorkspaceAccessDecision(
        can_view_metadata=can_view_metadata,
        can_view_content=can_view_content,
        reason=decision.reason,
    )
