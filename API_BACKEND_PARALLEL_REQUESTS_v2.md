# Backend Parallel Contract v2 (Django DRF)

Дата: 2026-04-15
Назначение: отдать backend-команде финальный список запросов, которые уже использует frontend, чтобы работать параллельно без блокеров.

Ссылка на frontend implementation:
- Building/Floor/Workspace/Profile
- Projects
- Company Admin
- Super Admin
- Platform Audit

## 1. Global rules

- Base URL: `/api` (или `/api/v1`, если есть версионирование).
- Формат: `application/json; charset=utf-8`.
- Предпочтительно `snake_case`.
- Frontend normalizers поддерживают и `snake_case`, и `camelCase` для ключевых полей.
- Ошибки DRF формата: `{ "detail": "..." }`.
- Status codes:
  - `200/201/204` success
  - `400` validation
  - `401` unauthorized/session expired
  - `403` forbidden
  - `404` not found
  - `409` conflict
  - `500` server error

---

## 2. Priority matrix

### P0 (нужно первым)
- Auth/session endpoints
- Building/Floor/Workspace/Profile (core employee flow)
- Projects (list/details/create/update/members)

### P1 (следом)
- Company Admin (overview/users/invites/roles)
- Super Admin (overview/tenants/platform users/invites)

### P2
- Platform Audit (stats/events/export CSV)

---

## 3. Endpoint map used by frontend

## 3.1 Auth + session

- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/session`
- `POST /api/auth/invite/activate`

Минимальный session payload:

```json
{
  "session": {
    "token": "...",
    "user": {
      "id": "u-1",
      "name": "Alex K",
      "email": "alex@company.com",
      "role": "employee",
      "department": "Marketing"
    }
  }
}
```

Roles:
- `employee`
- `manager`
- `company_admin`
- `super_admin`

## 3.2 Building / Floor / Workspace / Employee Profile

- `GET /api/buildings`
- `GET /api/buildings/{building_id}`
- `GET /api/buildings/{building_id}/departments`
- `GET /api/buildings/{building_id}/floors/{floor_id}/workspace`
- `GET /api/buildings/{building_id}/floors/{floor_id}/workspace/employee/{employee_id}`
- `GET /api/buildings/{building_id}/floors/{floor_id}/employees/{employee_id}/profile`

Supported aliases in frontend:
- `GET /api/buildings/{building_id}/floors/{floor_id}/workspace-context?employee_id={employee_id}`
- `GET /api/workspace/context?building_id={building_id}&floor_id={floor_id}&employee_id={employee_id}`
- `GET /api/employees/{employee_id}/profile?building_id={building_id}&floor_id={floor_id}`

## 3.3 Projects

- `GET /api/projects?q=&status=&department_id=&owner_id=`
- `GET /api/projects/{project_id}`
- `POST /api/projects`
- `PATCH /api/projects/{project_id}`
- `POST /api/projects/{project_id}/archive`
- `POST /api/projects/{project_id}/restore`
- `GET /api/projects/{project_id}/members`
- `POST /api/projects/{project_id}/members`
- `PATCH /api/projects/{project_id}/members/{member_id}`
- `DELETE /api/projects/{project_id}/members/{member_id}`

`Project.status` domain:
- `active | on_hold | completed | archived`

## 3.4 Company Admin

Primary endpoints (preferred):
- `GET /api/company/admin/overview`
- `GET /api/company/admin/departments`
- `GET /api/company/admin/users?q=&role=&status=&department_id=`
- `GET /api/company/admin/invites`
- `POST /api/company/admin/invites`
- `PATCH /api/company/admin/users/{user_id}/role`
- `POST /api/company/admin/invites/{invite_id}/revoke`

Supported aliases in frontend:
- `/api/admin/company/overview`
- `/api/admin/company/departments`
- `/api/admin/company/users`
- `/api/admin/company/invites`
- `/api/admin/company/users/{user_id}/role`
- `/api/admin/company/invites/{invite_id}/revoke`

## 3.5 Super Admin

Primary endpoints (preferred):
- `GET /api/admin/platform/overview`
- `GET /api/admin/platform/tenants?q=&status=`
- `GET /api/admin/platform/users`
- `GET /api/admin/platform/invites`
- `POST /api/admin/platform/tenants`
- `PATCH /api/admin/platform/tenants/{tenant_id}/status`
- `POST /api/admin/platform/invites`
- `POST /api/admin/platform/invites/{invite_id}/revoke`

Supported aliases in frontend:
- `/api/platform/admin/overview`
- `/api/platform/admin/tenants`
- `/api/platform/admin/users`
- `/api/platform/admin/invites`
- `/api/platform/admin/tenants/{tenant_id}/status`
- `/api/platform/admin/invites/{invite_id}/revoke`

## 3.6 Platform Audit

Primary endpoints:
- `GET /api/admin/platform/audit/stats`
- `GET /api/admin/platform/audit/events?q=&tenant_id=&action=&severity=&status=&from=&to=&page=&page_size=`
- `GET /api/admin/platform/audit/export?q=&tenant_id=&action=&severity=&status=&from=&to=`

Supported aliases in frontend:
- `/api/platform/admin/audit/stats`
- `/api/platform/admin/audit/events`
- `/api/platform/admin/audit/export`

Export format:
- `200 text/csv`
- `Content-Disposition: attachment; filename="platform-audit-YYYY-MM-DD.csv"`

---

## 4. Required schema domains

### Common statuses
- building/department status: `green | yellow | red`
- employee status: `online | call | vacation | sick`
- task column: `todo | in_progress | done`
- task priority: `high | medium | low`

### Projects
- project status: `active | on_hold | completed | archived`
- member role: `owner | editor | viewer`

### Company Admin
- company user role: `employee | manager | company_admin`
- company user status: `active | invited | blocked`
- company invite status: `pending | accepted | expired | revoked`

### Super Admin
- tenant status: `active | trial | suspended`
- platform role: `platform_admin | support | security`
- platform invite status: `pending | accepted | expired | revoked`

### Audit
- severity: `low | medium | high | critical`
- actor type: `user | system | integration`
- audit status: `success | failed`

---

## 5. Frontend compatibility notes

1. Frontend поддерживает fallback между primary endpoint и alias endpoint.
2. Для list endpoints поддерживаются форматы:
   - plain array
   - `{ "results": [...], "count": n }`
3. Для export CSV frontend ожидает текстовый контент.
4. При `401` frontend инвалидирует session и отправляет пользователя на login.

---

## 6. Release gate for backend handoff

1. OpenAPI (`/schema/`) содержит все endpoint'ы из раздела 3.
2. Swagger/ReDoc показывает схемы request/response без пустых placeholders.
3. Smoke (manual):
   - `VITE_API_SOURCE=live`
   - login -> workspace -> projects -> company admin -> super admin -> audit
4. Все `POST/PATCH/DELETE` endpoint'ы возвращают корректный формат (`200/201/204`).
5. Ошибки соответствуют DRF формату `{ "detail": "..." }`.

---

## 7. What backend team can start in parallel right now

1. Сделать DRF serializers + viewsets для sections `projects`, `company admin`, `super admin`, `audit`.
2. Поднять минимальные mock-like seed данные в dev DB.
3. Опубликовать OpenAPI schema и проверить endpoint coverage по этому документу.
4. Отдать frontend URL dev-среды и тестовый супер-админ аккаунт.
