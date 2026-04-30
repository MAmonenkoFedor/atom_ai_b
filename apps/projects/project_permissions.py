"""Project-level permission helpers used by API/views/services.

Single source of truth for project access. Callers (views, serializers,
queryset filters, services) MUST go through these helpers instead of
re-implementing role/membership/grant checks inline.

For list endpoints prefer :class:`ProjectAccessContext` to avoid per-row
N+1 hits on ``PermissionGrant`` / ``ProjectMember``.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.organizations.models import OrganizationMember
from apps.orgstructure.models import OrgUnitMember
from apps.projects.models import Project, ProjectMember

_PRIVILEGED_ROLE_CODES = frozenset({"admin", "company_admin", "super_admin", "executive", "ceo"})

PROJECT_SCOPE = "project"

PROJECT_CAPABILITY_CODES = {
    "can_edit_project": "project.edit",
    "can_view_documents": "docs.view",
    "can_upload_documents": "docs.upload",
    "can_edit_documents": "docs.edit",
    "can_delete_documents": "docs.delete",
    "can_assign_document_editors": "docs.assign_editors",
    "can_view_tasks": "tasks.view",
    "can_create_tasks": "tasks.create",
    "can_assign_tasks": "tasks.assign",
    "can_edit_tasks": "tasks.edit",
    "can_change_task_deadline": "tasks.change_deadline",
    "can_block_tasks": "tasks.block",
    "can_manage_members": "project.assign_members",
    "can_delegate_project_rights": "project.assign_rights",
    "can_moderate_chat": "project.chat.moderate",
}


def _user_role_code(user) -> str | None:
    if not user or not getattr(user, "is_authenticated", False):
        return None
    assignments = getattr(user, "role_assignments", None)
    if assignments is None:
        return None
    assignment = assignments.select_related("role").first()
    if not assignment or not getattr(assignment, "role", None):
        return None
    return assignment.role.code


def is_privileged_project_viewer(user) -> bool:
    role_code = _user_role_code(user)
    return bool(role_code and role_code in _PRIVILEGED_ROLE_CODES)


def get_project_membership(user, project: Project) -> ProjectMember | None:
    if not user or not getattr(user, "is_authenticated", False):
        return None
    return ProjectMember.objects.filter(project=project, user=user, is_active=True).first()


def _org_unit_ids_for_user(user) -> list[int]:
    if not user or not getattr(user, "is_authenticated", False):
        return []
    return list(OrgUnitMember.objects.filter(user=user).values_list("org_unit_id", flat=True))


def _access_project_ids_for_user(user) -> list[int]:
    if not user or not getattr(user, "is_authenticated", False):
        return []
    try:
        from apps.access.models import PermissionGrant
    except Exception:
        return []
    now = timezone.now()
    ids: list[int] = []
    grants = PermissionGrant.objects.filter(
        employee=user,
        scope_type=PROJECT_SCOPE,
        status=PermissionGrant.STATUS_ACTIVE,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).values_list("scope_id", flat=True)
    for raw in grants:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    return ids


def is_org_primary_stakeholder(user, project: Project) -> bool:
    """User belongs to the org unit set as the project's primary context (e.g. department)."""
    pk = getattr(project, "primary_org_unit_id", None)
    if pk is None:
        return False
    return OrgUnitMember.objects.filter(user=user, org_unit_id=pk).exists()


def is_org_unit_lead_for_project_primary(user, project: Project) -> bool:
    """Department lead for the project's primary org unit (seed: is_lead on OrgUnitMember)."""
    pk = getattr(project, "primary_org_unit_id", None)
    if pk is None:
        return False
    return OrgUnitMember.objects.filter(user=user, org_unit_id=pk, is_lead=True).exists()


def apply_project_list_visibility(qs, user):
    """
    Limit list queryset to projects the user may discover.
    - Privileged roles: all projects in organizations the user belongs to.
    - Manager: same as members OR projects whose primary org unit matches any of the user's units.
    - Others: created_by or any membership row (active or pending).
    """
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()

    access_project_ids = _access_project_ids_for_user(user)

    if is_privileged_project_viewer(user):
        org_ids = list(
            OrganizationMember.objects.filter(user=user, is_active=True).values_list("organization_id", flat=True)
        )
        if not org_ids:
            return qs.filter(pk__in=access_project_ids) if access_project_ids else qs.none()
        visible = qs.filter(organization_id__in=org_ids)
        if access_project_ids:
            visible = qs.filter(Q(pk__in=access_project_ids) | Q(organization_id__in=org_ids))
        return visible.distinct()

    member_q = Q(created_by=user) | Q(members__user=user)
    role_code = _user_role_code(user) or ""
    ou_ids = _org_unit_ids_for_user(user)
    if role_code == "manager" and ou_ids:
        scoped_q = member_q | Q(primary_org_unit_id__in=ou_ids)
        if access_project_ids:
            scoped_q |= Q(pk__in=access_project_ids)
        return qs.filter(scoped_q).distinct()
    if access_project_ids:
        member_q |= Q(pk__in=access_project_ids)
    return qs.filter(member_q).distinct()


def can_view_project(user, project: Project) -> bool:
    if is_privileged_project_viewer(user):
        return True
    if getattr(project, "created_by_id", None) == getattr(user, "id", None):
        return True
    if get_project_membership(user, project) is not None:
        return True
    if ProjectMember.objects.filter(project=project, user=user, is_active=False).exists():
        return True
    if project.pk in _access_project_ids_for_user(user):
        return True
    role_code = _user_role_code(user) or ""
    if role_code == "manager" and is_org_primary_stakeholder(user, project):
        return True
    return False


def can_manage_project(user, project: Project) -> bool:
    if is_privileged_project_viewer(user):
        return True
    membership = get_project_membership(user, project)
    if membership and membership.role in ProjectMember.MANAGE_ROLES:
        return True
    role_code = _user_role_code(user) or ""
    if role_code == "manager" and is_org_unit_lead_for_project_primary(user, project):
        return True
    return False


def has_project_access_permission(user, project: Project, permission_code: str) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    try:
        from apps.access.resolver import has_permission
    except Exception:
        return False
    try:
        return has_permission(
            user=user,
            permission_code=permission_code,
            scope_type=PROJECT_SCOPE,
            scope_id=str(project.pk),
        )
    except Exception:
        return False


def can_project_action(user, project: Project, permission_code: str, *, legacy_manage: bool = True) -> bool:
    if has_project_access_permission(user, project, permission_code):
        return True
    return bool(legacy_manage and can_manage_project(user, project))


def can_any_project_scoped(
    user,
    project: Project,
    *permission_codes: str,
    legacy_manage: bool = True,
) -> bool:
    return any(
        can_project_action(user, project, code, legacy_manage=legacy_manage) for code in permission_codes
    )


def _project_task_alias(legacy_tasks_code: str) -> str:
    """``tasks.create`` → ``project.tasks.create`` (project-scoped bundle)."""
    if legacy_tasks_code.startswith("tasks."):
        return f"project.{legacy_tasks_code}"
    return legacy_tasks_code


def can_project_task_action(
    user,
    project: Project,
    permission_code: str,
    *,
    legacy_manage: bool = True,
) -> bool:
    """Проектные задачи: ``tasks.*`` и зеркало ``project.tasks.*`` (lead bundle / delegation)."""
    if permission_code.startswith("tasks."):
        return can_any_project_scoped(
            user,
            project,
            permission_code,
            _project_task_alias(permission_code),
            legacy_manage=legacy_manage,
        )
    return can_project_action(user, project, permission_code, legacy_manage=legacy_manage)


def can_view_project_tasks(user, project: Project) -> bool:
    return can_view_project(user, project) or has_project_access_permission(
        user, project, "tasks.view"
    ) or has_project_access_permission(user, project, "project.tasks.view")


def project_capabilities(user, project: Project) -> dict[str, bool]:
    can_view = can_view_project(user, project)
    can_manage = can_manage_project(user, project)
    capabilities = {
        "can_view_project": can_view,
        "can_manage_project": can_manage,
    }
    for key, code in PROJECT_CAPABILITY_CODES.items():
        if key == "can_view_documents":
            capabilities[key] = can_view or has_project_access_permission(
                user, project, "docs.view"
            ) or has_project_access_permission(user, project, "project.docs.view")
        elif key == "can_upload_documents":
            capabilities[key] = can_any_project_scoped(
                user, project, "docs.upload", "project.docs.upload", legacy_manage=True
            )
        elif key == "can_edit_documents":
            capabilities[key] = can_any_project_scoped(
                user, project, "docs.edit", "project.docs.edit", legacy_manage=True
            )
        elif key == "can_assign_document_editors":
            capabilities[key] = can_any_project_scoped(
                user, project, "docs.assign_editors", "project.docs.assign_editors", legacy_manage=True
            )
        elif key == "can_view_tasks":
            capabilities[key] = can_view_project_tasks(user, project)
        elif key in ("can_create_tasks", "can_assign_tasks", "can_edit_tasks", "can_change_task_deadline", "can_block_tasks"):
            capabilities[key] = can_project_task_action(user, project, code, legacy_manage=True)
        elif key == "can_delegate_project_rights":
            # Delegating rights is intentionally explicit: owner/editor does not
            # imply rights delegation unless access service grants it.
            capabilities[key] = has_project_access_permission(user, project, code)
        else:
            capabilities[key] = can_project_action(user, project, code)
    return capabilities


def is_project_lead(user, project: Project) -> bool:
    """Глава проекта: флаг ``is_lead`` (v1) или устаревшая роль ``lead``."""

    membership = get_project_membership(user, project)
    if not membership:
        return False
    if getattr(membership, "is_lead", False):
        return True
    return membership.role == ProjectMember.ROLE_LEAD


def require_view_project(user, project: Project):
    """Gate project visibility via ``resolve_access`` (read or metadata-only)."""

    from apps.access.policies import resolve_access

    d = resolve_access(
        user=user,
        action="project.read",
        scope_type="project",
        scope_id=str(project.pk),
        resource=project,
    )
    if d.allowed:
        return d
    d2 = resolve_access(
        user=user,
        action="project.view_metadata",
        scope_type="project",
        scope_id=str(project.pk),
        resource=project,
    )
    if not d2.allowed:
        raise PermissionDenied("You do not have access to this project.")
    return d2


def require_manage_project(user, project: Project):
    """Legacy manage gate: membership manage roles (owner/lead/manager/editor)."""

    decision = compute_project_policy_decision(user, project)
    if decision.access_level not in {"manage", "admin"}:
        raise PermissionDenied("Only project owner or editor can modify this project.")
    return decision


_LEGACY_PERMISSION_TO_ACTION: dict[str, str] = {
    "project.edit": "project.update",
    "project.assign_members": "project.manage_members",
}


def require_project_action(user, project: Project, permission_code: str, message: str):
    action = _LEGACY_PERMISSION_TO_ACTION.get(permission_code, permission_code)
    return require_project_access(user, project, action, message)


def require_project_access(user, project: Project, action: str, message: str):
    from apps.access.policies import resolve_access

    d = resolve_access(
        user=user,
        action=action,
        scope_type="project",
        scope_id=str(project.pk),
        resource=project,
    )
    if not d.allowed:
        raise PermissionDenied(message)
    return d


def require_project_rights_delegation(user, project: Project) -> None:
    if not has_project_access_permission(user, project, "project.assign_rights"):
        raise PermissionDenied("You do not have permission to delegate project rights.")


# ---------------------------------------------------------------------------
# Semantic aliases — preferred for callers, reuse the helpers above.
# ---------------------------------------------------------------------------


def can_edit_project(user, project: Project) -> bool:
    return can_project_action(user, project, "project.edit")


def can_manage_project_members(user, project: Project) -> bool:
    return can_project_action(user, project, "project.assign_members")


def can_upload_project_docs(user, project: Project) -> bool:
    return can_any_project_scoped(user, project, "docs.upload", "project.docs.upload", legacy_manage=True)


def can_view_project_docs(user, project: Project) -> bool:
    return can_view_project(user, project) or has_project_access_permission(
        user, project, "docs.view"
    ) or has_project_access_permission(user, project, "project.docs.view")


def can_edit_project_docs(user, project: Project) -> bool:
    return can_any_project_scoped(user, project, "docs.edit", "project.docs.edit", legacy_manage=True)


def can_assign_project_doc_editors(user, project: Project) -> bool:
    return can_any_project_scoped(
        user, project, "docs.assign_editors", "project.docs.assign_editors", legacy_manage=True
    )


def can_create_project_tasks(user, project: Project) -> bool:
    return can_project_task_action(user, project, "tasks.create")


def can_assign_project_tasks(user, project: Project) -> bool:
    return can_project_task_action(user, project, "tasks.assign")


def can_change_project_task_deadline(user, project: Project) -> bool:
    return can_project_task_action(user, project, "tasks.change_deadline")


def can_block_project_tasks(user, project: Project) -> bool:
    return can_project_task_action(user, project, "tasks.block")


def can_moderate_project_chat(user, project: Project) -> bool:
    return can_project_action(user, project, "project.chat.moderate")


def can_delegate_project_rights(user, project: Project) -> bool:
    return has_project_access_permission(user, project, "project.assign_rights")


def compute_project_policy_decision(user, project: Project):
    """Derive maximum project access level for ``resolve_access`` / audits."""

    from apps.access.policies import PolicyDecision

    subject_id = int(getattr(user, "id", 0) or 0)
    scope_sid = str(project.pk)
    object_id = int(project.pk)

    if not user or not getattr(user, "is_authenticated", False):
        return PolicyDecision(
            allowed=False,
            access_level="none",
            reason="anonymous",
            scope_type="project",
            scope_id=scope_sid,
            subject_id=subject_id,
            object_id=object_id,
        )

    if bool(getattr(user, "is_superuser", False)):
        return PolicyDecision(
            allowed=True,
            access_level="admin",
            reason="superuser",
            scope_type="project",
            scope_id=scope_sid,
            subject_id=subject_id,
            object_id=object_id,
        )

    if is_privileged_project_viewer(user):
        return PolicyDecision(
            allowed=True,
            access_level="admin",
            reason="privileged_company_role",
            scope_type="project",
            scope_id=scope_sid,
            subject_id=subject_id,
            object_id=object_id,
        )

    if can_manage_project(user, project):
        return PolicyDecision(
            allowed=True,
            access_level="manage",
            reason="membership_manage",
            scope_type="project",
            scope_id=scope_sid,
            subject_id=subject_id,
            object_id=object_id,
        )

    if can_project_action(user, project, "project.edit", legacy_manage=True):
        return PolicyDecision(
            allowed=True,
            access_level="write",
            reason="permission:project.edit",
            scope_type="project",
            scope_id=scope_sid,
            subject_id=subject_id,
            object_id=object_id,
        )

    if can_view_project(user, project):
        return PolicyDecision(
            allowed=True,
            access_level="read",
            reason="project_visibility",
            scope_type="project",
            scope_id=scope_sid,
            subject_id=subject_id,
            object_id=object_id,
        )

    if has_project_access_permission(user, project, "project.view_metadata"):
        return PolicyDecision(
            allowed=True,
            access_level="metadata",
            reason="permission:project.view_metadata",
            scope_type="project",
            scope_id=scope_sid,
            subject_id=subject_id,
            object_id=object_id,
        )

    return PolicyDecision(
        allowed=False,
        access_level="none",
        reason="no_permission",
        scope_type="project",
        scope_id=scope_sid,
        subject_id=subject_id,
        object_id=object_id,
    )


# ---------------------------------------------------------------------------
# Bulk resolver — eliminates N+1 on list endpoints.
# ---------------------------------------------------------------------------


def _safe_project_id(scope_id) -> int | None:
    try:
        return int(scope_id)
    except (TypeError, ValueError):
        return None


class ProjectAccessContext:
    """Pre-loaded view of a single user's access to a set of projects.

    The context computes:

    * the user's privileged role code (if any),
    * org-unit memberships,
    * organisation memberships,
    * active project-scoped :class:`PermissionGrant`\\ s grouped by project id,
    * active :class:`ProjectMember` rows by project id.

    All ``can_*`` methods on this object are pure dict lookups — no SQL per
    project — so a list endpoint can serialise N projects with O(1) queries.
    """

    __slots__ = (
        "user",
        "_role_code",
        "_is_privileged",
        "_org_ids",
        "_org_unit_ids",
        "_grants_by_project",
        "_memberships_by_project",
        "_inactive_membership_ids",
        "_loaded_project_ids",
    )

    def __init__(self, user, projects: Sequence[Project] | Iterable[Project] | None = None):
        self.user = user
        self._role_code = _user_role_code(user)
        self._is_privileged = bool(
            self._role_code and self._role_code in _PRIVILEGED_ROLE_CODES
        )
        self._org_ids: set[int] = set()
        self._org_unit_ids: set[int] = set()
        self._grants_by_project: dict[int, list] = {}
        self._memberships_by_project: dict[int, ProjectMember] = {}
        self._inactive_membership_ids: set[int] = set()
        self._loaded_project_ids: set[int] = set()

        if user and getattr(user, "is_authenticated", False):
            self._org_ids = set(
                OrganizationMember.objects.filter(user=user, is_active=True).values_list(
                    "organization_id", flat=True
                )
            )
            self._org_unit_ids = set(
                OrgUnitMember.objects.filter(user=user).values_list(
                    "org_unit_id", flat=True
                )
            )
            self._load_project_grants(projects)

    # ---- loading helpers ----

    def _load_project_grants(self, projects):
        if not projects:
            return
        ids = {p.pk for p in projects if getattr(p, "pk", None)}
        new_ids = ids - self._loaded_project_ids
        if not new_ids:
            return
        try:
            from apps.access.models import PermissionGrant
        except Exception:
            self._loaded_project_ids |= new_ids
            return

        now = timezone.now()
        grants = (
            PermissionGrant.objects.filter(
                employee=self.user,
                scope_type=PROJECT_SCOPE,
                status=PermissionGrant.STATUS_ACTIVE,
            )
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        )
        for grant in grants:
            pid = _safe_project_id(grant.scope_id)
            if pid is None:
                continue
            self._grants_by_project.setdefault(pid, []).append(grant)

        memberships = ProjectMember.objects.filter(
            user=self.user, project_id__in=new_ids
        )
        for m in memberships:
            if m.is_active:
                self._memberships_by_project[m.project_id] = m
            else:
                self._inactive_membership_ids.add(m.project_id)

        self._loaded_project_ids |= new_ids

    def ensure(self, project: Project) -> None:
        if project.pk not in self._loaded_project_ids:
            self._load_project_grants([project])

    # ---- accessors ----

    @property
    def role_code(self) -> str | None:
        return self._role_code

    def grants_for(self, project: Project) -> list:
        self.ensure(project)
        return list(self._grants_by_project.get(project.pk, []))

    def membership_for(self, project: Project) -> ProjectMember | None:
        self.ensure(project)
        return self._memberships_by_project.get(project.pk)

    def has_inactive_membership(self, project: Project) -> bool:
        self.ensure(project)
        return project.pk in self._inactive_membership_ids

    def has_permission(self, project: Project, permission_code: str) -> bool:
        for grant in self.grants_for(project):
            if grant.permission_code == permission_code:
                return True
        return False

    # ---- policy decisions ----

    def can_view_project(self, project: Project) -> bool:
        if not self.user or not getattr(self.user, "is_authenticated", False):
            return False
        if self._is_privileged:
            return True
        if getattr(project, "created_by_id", None) == getattr(self.user, "id", None):
            return True
        if self.membership_for(project) is not None:
            return True
        if self.has_inactive_membership(project):
            return True
        if self.grants_for(project):
            return True
        if (
            self._role_code == "manager"
            and getattr(project, "primary_org_unit_id", None) in self._org_unit_ids
        ):
            return True
        return False

    def can_manage_project(self, project: Project) -> bool:
        if self._is_privileged:
            return True
        membership = self.membership_for(project)
        if membership and membership.role in ProjectMember.MANAGE_ROLES:
            return True
        if (
            self._role_code == "manager"
            and getattr(project, "primary_org_unit_id", None) in self._org_unit_ids
        ):
            ou_id = project.primary_org_unit_id
            if OrgUnitMember.objects.filter(
                user=self.user, org_unit_id=ou_id, is_lead=True
            ).exists():
                return True
        return False

    def can_action(self, project: Project, permission_code: str, *, legacy_manage: bool = True) -> bool:
        if self.has_permission(project, permission_code):
            return True
        return bool(legacy_manage and self.can_manage_project(project))

    def can_any_scoped(self, project: Project, *codes: str, legacy_manage: bool = True) -> bool:
        return any(self.can_action(project, code, legacy_manage=legacy_manage) for code in codes)

    def can_view_project_tasks(self, project: Project) -> bool:
        return self.can_view_project(project) or self.has_permission(project, "tasks.view") or self.has_permission(
            project, "project.tasks.view"
        )

    def can_project_task_action(self, project: Project, permission_code: str) -> bool:
        if permission_code.startswith("tasks."):
            return self.can_any_scoped(
                project, permission_code, _project_task_alias(permission_code), legacy_manage=True
            )
        return self.can_action(project, permission_code)

    def capabilities(self, project: Project) -> dict[str, bool]:
        can_view = self.can_view_project(project)
        can_manage = self.can_manage_project(project)
        out = {
            "can_view_project": can_view,
            "can_manage_project": can_manage,
        }
        for key, code in PROJECT_CAPABILITY_CODES.items():
            if key == "can_view_documents":
                out[key] = can_view or self.has_permission(project, "docs.view") or self.has_permission(
                    project, "project.docs.view"
                )
            elif key == "can_upload_documents":
                out[key] = self.can_any_scoped(
                    project, "docs.upload", "project.docs.upload", legacy_manage=True
                )
            elif key == "can_edit_documents":
                out[key] = self.can_any_scoped(
                    project, "docs.edit", "project.docs.edit", legacy_manage=True
                )
            elif key == "can_assign_document_editors":
                out[key] = self.can_any_scoped(
                    project, "docs.assign_editors", "project.docs.assign_editors", legacy_manage=True
                )
            elif key == "can_view_tasks":
                out[key] = self.can_view_project_tasks(project)
            elif key in (
                "can_create_tasks",
                "can_assign_tasks",
                "can_edit_tasks",
                "can_change_task_deadline",
                "can_block_tasks",
            ):
                out[key] = self.can_project_task_action(project, code)
            elif key == "can_delegate_project_rights":
                out[key] = self.has_permission(project, code)
            else:
                out[key] = self.can_action(project, code)
        return out

    def access_source(self, project: Project) -> dict:
        """Explain *why* the user can/can't see this project (debug payload)."""

        grants = self.grants_for(project)
        membership = self.membership_for(project)
        return {
            "is_privileged_role": self._is_privileged,
            "role_code": self._role_code,
            "is_creator": getattr(project, "created_by_id", None) == getattr(self.user, "id", None),
            "membership_role": getattr(membership, "role", None),
            "has_inactive_membership": self.has_inactive_membership(project),
            "is_org_primary_stakeholder": getattr(project, "primary_org_unit_id", None)
            in self._org_unit_ids,
            "direct_grants": [
                {
                    "id": g.id,
                    "permission_code": g.permission_code,
                    "grant_mode": g.grant_mode,
                    "expires_at": g.expires_at.isoformat() if g.expires_at else None,
                    "source_type": g.source_type,
                    "parent_grant_id": g.parent_grant_id,
                }
                for g in grants
                if g.source_type != "delegation"
            ],
            "delegated_grants": [
                {
                    "id": g.id,
                    "permission_code": g.permission_code,
                    "grant_mode": g.grant_mode,
                    "expires_at": g.expires_at.isoformat() if g.expires_at else None,
                    "parent_grant_id": g.parent_grant_id,
                }
                for g in grants
                if g.source_type == "delegation"
            ],
        }


def bulk_project_capabilities(
    user, projects: Sequence[Project]
) -> dict[int, dict[str, bool]]:
    """One-shot capability resolution for a list endpoint."""

    ctx = ProjectAccessContext(user, projects)
    return {project.pk: ctx.capabilities(project) for project in projects}
