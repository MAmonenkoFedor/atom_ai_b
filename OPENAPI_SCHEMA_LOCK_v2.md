# OpenAPI Schema Lock v2 (Frontend ↔ Django DRF)

Дата фиксации: 2026-04-15
Базовый префикс: `/api`

Этот документ фиксирует финальные URL и целевые схемы OpenAPI для Backend Alignment Sprint.

## 1) Projects

## 1.1 Endpoints
- `GET /api/projects`
- `GET /api/projects/{project_id}`
- `POST /api/projects`
- `PATCH /api/projects/{project_id}`
- `POST /api/projects/{project_id}/archive`
- `POST /api/projects/{project_id}/restore`
- `GET /api/projects/{project_id}/members`
- `POST /api/projects/{project_id}/members`
- `PATCH /api/projects/{project_id}/members/{member_id}`
- `DELETE /api/projects/{project_id}/members/{member_id}`

## 1.2 Query params
- `q`
- `status` (`active|on_hold|completed|archived`)
- `department_id`
- `owner_id`

## 1.3 Schemas
- `Project`
- `ProjectListResponse`
- `CreateProjectRequest`
- `UpdateProjectRequest`
- `ProjectMember`
- `CreateProjectMemberRequest`
- `UpdateProjectMemberRequest`

---

## 2) Company Admin

## 2.1 Primary endpoints
- `GET /api/company/admin/overview`
- `GET /api/company/admin/departments`
- `GET /api/company/admin/users`
- `GET /api/company/admin/invites`
- `POST /api/company/admin/invites`
- `PATCH /api/company/admin/users/{user_id}/role`
- `POST /api/company/admin/invites/{invite_id}/revoke`

## 2.2 Alias endpoints (optional, but supported in frontend)
- `/api/admin/company/*`

## 2.3 Query params
- users: `q`, `role`, `status`, `department_id`

## 2.4 Schemas
- `CompanyAdminOverview`
- `CompanyDepartmentSummary`
- `CompanyUserSummary`
- `CompanyInvite`
- `CreateCompanyInviteRequest`
- `UpdateCompanyUserRoleRequest`

---

## 3) Super Admin

## 3.1 Primary endpoints
- `GET /api/admin/platform/overview`
- `GET /api/admin/platform/tenants`
- `GET /api/admin/platform/users`
- `GET /api/admin/platform/invites`
- `POST /api/admin/platform/tenants`
- `PATCH /api/admin/platform/tenants/{tenant_id}/status`
- `POST /api/admin/platform/invites`
- `POST /api/admin/platform/invites/{invite_id}/revoke`

## 3.2 Alias endpoints
- `/api/platform/admin/*`

## 3.3 Query params
- tenants: `q`, `status` (`active|trial|suspended`)

## 3.4 Schemas
- `SuperAdminOverview`
- `TenantSummary`
- `PlatformUserSummary`
- `PlatformInvite`
- `CreateTenantRequest`
- `UpdateTenantStatusRequest`
- `CreatePlatformInviteRequest`

---

## 4) Platform Audit

## 4.1 Primary endpoints
- `GET /api/admin/platform/audit/stats`
- `GET /api/admin/platform/audit/events`
- `GET /api/admin/platform/audit/export`

## 4.2 Alias endpoints
- `/api/platform/admin/audit/*`

## 4.3 Query params
- `q`
- `tenant_id`
- `action`
- `severity` (`low|medium|high|critical`)
- `status` (`success|failed`)
- `from`
- `to`
- `page`
- `page_size`

## 4.4 Schemas
- `PlatformAuditStats`
- `PlatformAuditEvent`
- `PlatformAuditListResponse`

## 4.5 Export response
- Content type: `text/csv`
- Header: `Content-Disposition: attachment; filename="platform-audit-YYYY-MM-DD.csv"`

---

## 5) Admin Action Center

## 5.1 Primary endpoints
- `GET /api/admin/actions/stats`
- `GET /api/admin/actions/events`
- `GET /api/admin/actions/events/{action_id}`

## 5.2 Alias endpoints
- `/api/admin/action-center/*`

## 5.3 Query params
- `q`
- `scope` (`company|platform`)
- `severity` (`low|medium|high|critical`)
- `status` (`success|failed`)
- `action`
- `actor`
- `from`
- `to`
- `page`
- `page_size`

## 5.4 Schemas
- `AdminActionStats`
- `AdminActionEvent`
- `AdminActionListResponse`
- `AdminActionDetails`

---

## 6) Cross-cutting schema rules

1. Плоский list-формат допускается, но целевой формат:

```json
{ "count": 0, "results": [] }
```

2. Ошибки в DRF формате:

```json
{ "detail": "..." }
```

3. Для nullable полей использовать явный `nullable: true` в OpenAPI.

4. Для enums использовать отдельные `enum` в схемах, а не свободные string.

5. Для дат использовать формат `date-time` (ISO 8601) где возможно.
