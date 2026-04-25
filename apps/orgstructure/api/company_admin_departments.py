"""Company admin: отделы (OrgUnit) из БД — список, создание, назначение руководителя."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access.models import PermissionDefinition, PermissionGrant, SCOPE_DEPARTMENT
from apps.access.service import grant_permission, revoke_permission
from apps.audit.models import AuditEvent
from apps.audit.service import emit_audit_event
from apps.core.api.permissions import IsCompanyAdminOrSuperAdmin, normalized_roles_for_user
from apps.organizations.models import Organization, OrganizationMember
from apps.orgstructure.models import OrgUnit, OrgUnitMember
from apps.projects.models import Project

User = get_user_model()


def _dept_lead_scoped_note(org_unit_id: int) -> str:
    return f"dept_lead_scoped:ou={int(org_unit_id)}"


def _user_label(u) -> str:
    if not u:
        return "—"
    return (u.get_full_name() or getattr(u, "username", None) or "").strip() or "—"


HISTORY_TYPES = ("org.department_lead_set", "org.department_lead_cleared")
HISTORY_PER_DEPT = 8


def _revoke_dept_lead_scoped_grants(*, employee, org_unit_id: int, revoked_by, request) -> int:
    """Снимает выданные вместе с руководством права на отдел (ищет по note)."""
    n = 0
    note = _dept_lead_scoped_note(org_unit_id)
    qs = PermissionGrant.objects.filter(
        employee=employee,
        status=PermissionGrant.STATUS_ACTIVE,
        scope_type=SCOPE_DEPARTMENT,
        scope_id=str(org_unit_id),
        note=note,
    )
    for g in list(qs):
        revoke_permission(
            g,
            revoked_by=revoked_by,
            note="department_lead_scoped_revoke",
            request=request,
        )
        n += 1
    return n


def _company_admin_org_ids(user) -> list[int] | None:
    """None = super_admin (доступ ко всем организациям при явном organization_id)."""
    roles = normalized_roles_for_user(user)
    if "super_admin" in roles:
        return None
    return list(
        OrganizationMember.objects.filter(user=user, is_active=True).values_list(
            "organization_id", flat=True
        )
    )


def _batch_department_payload(ous: list[OrgUnit]) -> list[dict]:
    """Сводка отдела для списка: глава, пакетные права, краткая история смены главы (из AuditEvent)."""
    if not ous:
        return []
    ou_ids = [ou.id for ou in ous]
    str_ids = [str(oid) for oid in ou_ids]
    # Главы
    lead_rows = {
        m.org_unit_id: m.user
        for m in OrgUnitMember.objects.filter(org_unit_id__in=ou_ids, is_lead=True).select_related(
            "user"
        )
    }
    ec_rows = {row["org_unit_id"]: row["n"] for row in list(
        OrgUnitMember.objects.filter(org_unit_id__in=ou_ids)
        .values("org_unit_id")
        .annotate(n=Count("id"))
    )}
    for oid in ou_ids:
        if oid not in ec_rows:
            ec_rows[oid] = 0
    proj_rows = {row["primary_org_unit_id"]: row["n"] for row in list(
        Project.objects.filter(
            primary_org_unit_id__in=ou_ids, status=Project.STATUS_ACTIVE
        )
        .values("primary_org_unit_id")
        .annotate(n=Count("id"))
    )}
    for oid in ou_ids:
        if oid not in proj_rows:
            proj_rows[oid] = 0

    # Пакетные гранты текущей главы (тот же note, что при выдаче с назначением)
    note_in = [_dept_lead_scoped_note(oid) for oid in ou_ids]
    gmap: dict[tuple[int, int], list[str]] = {}
    for g in PermissionGrant.objects.filter(
        status=PermissionGrant.STATUS_ACTIVE,
        scope_type=SCOPE_DEPARTMENT,
        note__in=note_in,
    ).values("employee_id", "permission_code", "scope_id"):
        sid = (g.get("scope_id") or "").strip()
        if not sid.isdigit():
            continue
        k = (int(sid), int(g["employee_id"]))
        gmap.setdefault(k, []).append(g["permission_code"])
    all_codes: set[str] = set()
    for codes in gmap.values():
        all_codes.update(codes)
    code_names: dict[str, str] = {}
    if all_codes:
        for row in PermissionDefinition.objects.filter(code__in=sorted(all_codes)).values("code", "name"):
            code_names[row["code"]] = row["name"]

    # История: последние события на отдел, до HISTORY_PER_DEPT на каждый
    h_buf: dict[int, list[AuditEvent]] = {oid: [] for oid in ou_ids}
    event_cap = min(2000, max(80, 12 * len(ou_ids)))
    for ev in (
        AuditEvent.objects.filter(
            entity_type="org_unit",
            entity_id__in=str_ids,
            event_type__in=HISTORY_TYPES,
        )
        .select_related("actor")
        .order_by("-created_at")[:event_cap]
    ):
        eid = int(ev.entity_id) if (ev.entity_id or "").isdigit() else None
        if eid is None or eid not in h_buf:
            continue
        if len(h_buf[eid]) >= HISTORY_PER_DEPT:
            continue
        h_buf[eid].append(ev)
    subj_ids: set[int] = set()
    for el in h_buf.values():
        for ev in el:
            raw = (ev.payload or {}).get("user_id")
            if raw is not None and str(raw).isdigit():
                subj_ids.add(int(raw))
    subj_name: dict[int, str] = {}
    if subj_ids:
        for u in User.objects.filter(id__in=subj_ids):
            subj_name[u.id] = _user_label(u)

    out: list[dict] = []
    for ou in ous:
        u = lead_rows.get(ou.id)
        if u:
            lead_name = (u.get_full_name() or u.username or "").strip() or "-"
        else:
            lead_name = "-"
        lead_user_id = u.id if u else None
        lead_email = (u.email or "").strip() if u else ""
        p_codes: list[str] = []
        if u:
            p_codes = sorted(gmap.get((ou.id, u.id), []))
        bundle = [{"code": c, "name": code_names.get(c) or c} for c in p_codes]
        history: list[dict] = []
        for ev in h_buf.get(ou.id, []):
            p = ev.payload or {}
            suid = p.get("user_id")
            sid_int = int(suid) if suid is not None and str(suid).isdigit() else None
            history.append(
                {
                    "at": ev.created_at.isoformat(),
                    "action": ev.action,
                    "event_type": ev.event_type,
                    "actor_id": ev.actor_id,
                    "actor_name": _user_label(ev.actor) if ev.actor else "—",
                    "subject_user_id": suid,
                    "subject_name": (subj_name.get(sid_int) if sid_int is not None else "—")
                    or "—",
                    "grant_dept_edit": p.get("grant_dept_edit"),
                    "grant_dept_assign_members": p.get("grant_dept_assign_members"),
                }
            )
        out.append(
            {
                "id": ou.id,
                "name": ou.name,
                "code": ou.code or "",
                "description": getattr(ou, "description", "") or "",
                "created_at": ou.created_at.isoformat() if getattr(ou, "created_at", None) else None,
                "lead": lead_name,
                "lead_user_id": lead_user_id,
                "lead_email": lead_email,
                "employees_total": ec_rows.get(ou.id, 0),
                "active_projects_total": proj_rows.get(ou.id, 0),
                "open_tasks_total": 0,
                "status": "green",
                "lead_bundle_permissions": bundle,
                "lead_history": history,
            }
        )
    return out


def _serialize_department(ou: OrgUnit) -> dict:
    rows = _batch_department_payload([ou])
    return rows[0] if rows else {}


class CompanyAdminDepartmentsView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    def get(self, request):
        org_ids = _company_admin_org_ids(request.user)
        qs = OrgUnit.objects.filter(is_active=True).select_related("organization").order_by("name")
        if org_ids is not None:
            if not org_ids:
                return Response([])
            raw_oid = request.query_params.get("organization_id")
            if raw_oid not in (None, ""):
                oid = int(raw_oid)
                if oid not in org_ids:
                    raise PermissionDenied("Нет доступа к этой организации.")
                qs = qs.filter(organization_id=oid)
            else:
                qs = qs.filter(organization_id__in=org_ids)
        else:
            raw_oid = request.query_params.get("organization_id")
            if raw_oid not in (None, ""):
                qs = qs.filter(organization_id=int(raw_oid))
            else:
                org_pk_cap = list(
                    Organization.objects.filter(is_active=True).values_list("id", flat=True)[:200]
                )
                qs = qs.filter(organization_id__in=org_pk_cap)
        return Response(_batch_department_payload(list(qs)))

    def post(self, request):
        name = (request.data.get("name") or "").strip()
        if not name:
            raise ValidationError({"name": "Укажите название отдела."})
        code = (request.data.get("code") or "").strip()
        parent_id = request.data.get("parent_id")
        roles = normalized_roles_for_user(request.user)
        org_ids = _company_admin_org_ids(request.user)
        raw_org = request.data.get("organization_id")

        if "super_admin" in roles:
            if raw_org in (None, ""):
                raise ValidationError({"organization_id": "Укажите организацию."})
            org = get_object_or_404(Organization, pk=int(raw_org), is_active=True)
        else:
            if not org_ids:
                raise ValidationError({"detail": "Нет активного членства в организации."})
            if raw_org not in (None, ""):
                oid = int(raw_org)
                if oid not in org_ids:
                    raise PermissionDenied("Нет доступа к этой организации.")
                org = Organization.objects.get(pk=oid)
            else:
                org = Organization.objects.get(pk=org_ids[0])

        parent = None
        if parent_id not in (None, ""):
            parent = get_object_or_404(OrgUnit, pk=int(parent_id), is_active=True)
            if parent.organization_id != org.id:
                raise ValidationError({"parent_id": "Родительский отдел из другой организации."})

        desc = (request.data.get("description") or "").strip()
        try:
            ou = OrgUnit.objects.create(
                organization=org,
                name=name,
                code=code,
                parent=parent,
                description=desc,
                is_active=True,
            )
        except IntegrityError as exc:
            raise ValidationError(
                {"name": "Отдел с таким названием уже существует в организации."}
            ) from exc
        return Response(_serialize_department(ou), status=status.HTTP_201_CREATED)


class CompanyAdminDepartmentDetailView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    def _get_department_for_user(self, request, department_id: int) -> OrgUnit:
        ou = get_object_or_404(OrgUnit, pk=department_id, is_active=True)
        org_ids = _company_admin_org_ids(request.user)
        if org_ids is not None and ou.organization_id not in org_ids:
            raise PermissionDenied("Нет доступа к этому отделу.")
        return ou

    def patch(self, request, department_id: int):
        ou = self._get_department_for_user(request, department_id)
        changed_fields: list[str] = []

        if "name" in request.data:
            name = (request.data.get("name") or "").strip()
            if not name:
                raise ValidationError({"name": "Название отдела не может быть пустым."})
            if name != ou.name:
                ou.name = name
                changed_fields.append("name")

        if "code" in request.data:
            code = (request.data.get("code") or "").strip()
            if code != (ou.code or ""):
                ou.code = code
                changed_fields.append("code")

        if "description" in request.data:
            description = (request.data.get("description") or "").strip()
            if description != (ou.description or ""):
                ou.description = description
                changed_fields.append("description")

        if not changed_fields:
            return Response(_serialize_department(ou))

        try:
            ou.save(update_fields=changed_fields)
        except IntegrityError as exc:
            raise ValidationError(
                {"name": "Отдел с таким названием уже существует в организации."}
            ) from exc

        try:
            emit_audit_event(
                request,
                event_type="org.department_updated",
                action="update_department",
                entity_type="org_unit",
                entity_id=str(ou.id),
                payload={"changed_fields": changed_fields},
            )
        except Exception:
            pass
        return Response(_serialize_department(ou))

    def delete(self, request, department_id: int):
        ou = self._get_department_for_user(request, department_id)

        if OrgUnit.objects.filter(parent_id=ou.id, is_active=True).exists():
            raise ValidationError(
                {"detail": "Нельзя удалить отдел, пока у него есть активные подотделы."}
            )

        if OrgUnitMember.objects.filter(org_unit=ou).exists():
            raise ValidationError(
                {"detail": "Нельзя удалить отдел, пока в нём есть сотрудники."}
            )

        if Project.objects.filter(primary_org_unit=ou).exclude(
            status=Project.STATUS_ARCHIVED
        ).exists():
            raise ValidationError(
                {
                    "detail": (
                        "Нельзя удалить отдел, пока к нему привязаны активные/незакрытые проекты."
                    )
                }
            )

        ou.is_active = False
        ou.save(update_fields=["is_active"])

        try:
            emit_audit_event(
                request,
                event_type="org.department_deleted",
                action="delete_department",
                entity_type="org_unit",
                entity_id=str(ou.id),
                payload={"organization_id": ou.organization_id},
            )
        except Exception:
            pass
        return Response({"status": "deleted"}, status=status.HTTP_200_OK)


class CompanyAdminDepartmentLeadView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperAdmin]

    def post(self, request, department_id: int):
        raw_uid = request.data.get("user_id")
        if raw_uid in (None, ""):
            raise ValidationError({"user_id": "Укажите пользователя."})
        uid = int(raw_uid)
        grant_dept_edit = bool(request.data.get("grant_dept_edit", False))
        grant_dept_assign = bool(request.data.get("grant_dept_assign_members", False))
        ou = get_object_or_404(OrgUnit, pk=department_id, is_active=True)
        org_ids = _company_admin_org_ids(request.user)
        if org_ids is not None and ou.organization_id not in org_ids:
            raise PermissionDenied("Нет доступа к этому отделу.")

        user = get_object_or_404(User, pk=uid)
        if not OrganizationMember.objects.filter(
            user=user, organization=ou.organization, is_active=True
        ).exists():
            raise ValidationError({"user_id": "Пользователь не состоит в этой организации."})

        old_lead_id = None
        prev = (
            OrgUnitMember.objects.filter(org_unit=ou, is_lead=True).values_list("user_id", flat=True).first()
        )
        if prev and prev != uid:
            old_lead_id = int(prev)

        with transaction.atomic():
            if old_lead_id:
                old_user = User.objects.get(pk=old_lead_id)
                _revoke_dept_lead_scoped_grants(
                    employee=old_user,
                    org_unit_id=ou.id,
                    revoked_by=request.user,
                    request=request,
                )
            OrgUnitMember.objects.filter(org_unit=ou, is_lead=True).exclude(user_id=uid).update(
                is_lead=False
            )
            OrgUnitMember.objects.update_or_create(
                org_unit=ou,
                user=user,
                defaults={"is_lead": True},
            )
            _revoke_dept_lead_scoped_grants(
                employee=user,
                org_unit_id=ou.id,
                revoked_by=request.user,
                request=request,
            )
            note = _dept_lead_scoped_note(ou.id)
            grant_mode = PermissionGrant.GRANT_MODE_USE_AND_DELEGATE
            if grant_dept_edit:
                grant_permission(
                    employee=user,
                    permission_code="department.edit",
                    scope_type=SCOPE_DEPARTMENT,
                    scope_id=str(ou.id),
                    grant_mode=grant_mode,
                    granted_by=request.user,
                    note=note,
                    request=request,
                )
            if grant_dept_assign:
                grant_permission(
                    employee=user,
                    permission_code="department.assign_members",
                    scope_type=SCOPE_DEPARTMENT,
                    scope_id=str(ou.id),
                    grant_mode=grant_mode,
                    granted_by=request.user,
                    note=note,
                    request=request,
                )

        try:
            emit_audit_event(
                request,
                event_type="org.department_lead_set",
                action="set_lead",
                entity_type="org_unit",
                entity_id=str(ou.id),
                payload={
                    "org_unit_id": ou.id,
                    "organization_id": ou.organization_id,
                    "user_id": uid,
                    "grant_dept_edit": grant_dept_edit,
                    "grant_dept_assign_members": grant_dept_assign,
                },
            )
        except Exception:
            pass
        return Response(_serialize_department(ou))

    def delete(self, request, department_id: int):
        """Снять руководителя и отозвать выданные вместе с ним отдел-скоупы."""
        ou = get_object_or_404(OrgUnit, pk=department_id, is_active=True)
        org_ids = _company_admin_org_ids(request.user)
        if org_ids is not None and ou.organization_id not in org_ids:
            raise PermissionDenied("Нет доступа к этому отделу.")

        lead = OrgUnitMember.objects.filter(org_unit=ou, is_lead=True).select_related("user").first()
        if not lead or not lead.user_id:
            raise ValidationError({"detail": "Назначенного руководителя нет."})

        u = lead.user
        with transaction.atomic():
            _revoke_dept_lead_scoped_grants(
                employee=u,
                org_unit_id=ou.id,
                revoked_by=request.user,
                request=request,
            )
            lead.is_lead = False
            lead.save(update_fields=["is_lead"])

        try:
            emit_audit_event(
                request,
                event_type="org.department_lead_cleared",
                action="clear_lead",
                entity_type="org_unit",
                entity_id=str(ou.id),
                payload={
                    "org_unit_id": ou.id,
                    "organization_id": ou.organization_id,
                    "user_id": u.id,
                },
            )
        except Exception:
            pass
        return Response(_serialize_department(ou))