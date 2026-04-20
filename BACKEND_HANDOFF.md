# Backend Handoff

Дата: 2026-04-17
Статус: canonical backend handoff

## 1. Назначение документа

Этот файл является главным backend-документом для параллельной работы frontend и backend.
Именно он считается каноническим источником API-контракта до публикации финального OpenAPI.

Документ фиксирует:
- canonical endpoints;
- поддерживаемые alias paths;
- deprecated paths, которые нельзя считать целевыми;
- обязательные schema domains и integration rules;
- минимальный набор runtime expectations для live-интеграции.

Правило пакета документации:
- `docs/backend/BACKEND_HANDOFF.md` — канонический API contract;
- mini-spec в `docs/product/*` обязаны соответствовать этому документу;
- любые contract changes сначала вносятся сюда и в OpenAPI, потом в mini-spec и frontend.

## 2. Integration rules

- Base URL: `/api`.
- Формат: `application/json; charset=utf-8`.
- Целевой naming: `snake_case`.
- DRF error format:
  - `{ "detail": "..." }`
- HTTP status policy:
  - `200/201/204` success
  - `400` validation error
  - `401` unauthorized or session expired
  - `403` forbidden
  - `404` not found
  - `409` conflict
  - `500` server error

## 3. Frontend runtime expectations

Frontend env baseline:

```env
VITE_API_SOURCE=live
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_API_PREFIX=/api
VITE_API_MOCK_FALLBACK=true
VITE_API_MOCK_LATENCY_MS=120
```

Режимы:
- `VITE_API_SOURCE=mock` — frontend полностью работает на mock layer.
- `VITE_API_SOURCE=live` — frontend работает против Django DRF.
- `VITE_API_MOCK_FALLBACK=true` — live failure может временно откатить вызов на mock.
- Для честного integration smoke нужен режим `VITE_API_MOCK_FALLBACK=false`.

## 4. Priority domains

### P0
- Auth / Session / Invite
- Buildings / Floors / Workspace / Employee Profile
- Tasks
- Projects

### P1
- Company Admin
- Super Admin
- Admin Action Center

### P2
- Platform Audit
- Executive aggregate domain

## 5. Canonical endpoint map

### 5.1 Auth / Session / Invite

Canonical endpoints:
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/session`
- `GET /api/auth/invite/{token}`
- `POST /api/auth/invite/activate`

Deprecated endpoints:
- `GET /api/auth/me`
- `POST /api/auth/invite/{token}/activate`

Invite activation request:

```json
{
  "token": "invite-token",
  "password": "secret",
  "full_name": "Alex Kim"
}
```

Session response minimum:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_at": "2026-04-17T18:00:00Z",
  "user": {
    "id": "u-1",
    "email": "alex@company.com",
    "full_name": "Alex Kim",
    "role": "executive",
    "company_id": "company-main",
    "department_id": "marketing"
  }
}
```

Role set:
- `employee`
- `manager`
- `company_admin`
- `executive`
- `super_admin`

### 5.2 Organization / Workspace / Employee Profile

Canonical endpoints (floor-scoped):
- `GET /api/buildings`
- `GET /api/buildings/{building_id}`
- `GET /api/buildings/{building_id}/departments`
- `GET /api/buildings/{building_id}/floors/{floor_id}/workspace`
- `GET /api/buildings/{building_id}/floors/{floor_id}/workspace/employee/{employee_id}`
- `GET /api/buildings/{building_id}/floors/{floor_id}/employees/{employee_id}/profile`

Supported aliases (floor-scoped):
- `GET /api/buildings/{building_id}/floors/{floor_id}/workspace-context?employee_id={employee_id}`
- `GET /api/workspace/context?building_id={building_id}&floor_id={floor_id}&employee_id={employee_id}`
- `GET /api/employees/{employee_id}/profile?building_id={building_id}&floor_id={floor_id}`

Path/query rules:
- canonical nested endpoints используют `building_id` и `floor_id` как path params;
- alias endpoints обязаны принимать `building_id` и `floor_id` как query params;
- `employee_id` обязателен либо в path, либо в query в зависимости от route shape.

#### 5.2.1 Employee Cabinet (self-service)

«Employee cabinet» — enriched workspace текущего пользователя (независимо от floor/building context). Эти endpoint-ы резолвят текущего пользователя из access token / cookie session.

Canonical endpoints:
- `GET /api/workspace` — обогащенный workspace текущего пользователя (см. `WorkspaceData` в `src/entities/workspace/types.ts`);
- `GET /api/employees/me` — owner-mode профиль (`MyEmployeeProfile`);
- `GET /api/employees/{employee_id}` — profile view: вернёт `view: "owner"` если `employee_id` совпадает с текущим пользователем, иначе `view: "public"` (`PublicEmployeeProfile`);
- `PATCH /api/employees/me` — обновление редактируемых полей (`UpdateMyEmployeeProfileInput`);
- `POST /api/workspace/quick-tasks` — быстрое создание задачи из Workspace (`CreateQuickTaskInput` → `CreateQuickTaskResult`).

Ответ `GET /api/workspace` должен включать следующие опциональные блоки (frontend их рендерит при наличии, иначе gracefully деградирует):
- `greeting` — `{ userName, timeGreeting, focusMessage, aiTip? }`;
- `todayFocus` — `{ date, primaryGoal, meetingsCount, tasksDueToday, tasksOverdue, aiSuggestion? }`;
- `quickActions` — массив быстрых действий; `kind` ∈ `create_task | open_ai | new_note | set_status | open_calendar`;
- `stats` — счётчики и бейджи (`tasksInProgress`, `tasksDone`, `tasksOverdue`, `streakDays`, `weekBalance`);
- `tasksGrouped` — группы `overdue | today | this_week | later | done`;
- `aiContext` — контекстный bundle для inline AI и full-screen chat (employee meta, `openTaskIds`, `suggestedPrompts`);
- `roleExtras` — вариативная секция: `{ kind: "manager" | "admin" | "executive", ... }`;
- `viewerRole` — роль владельца сессии (для удобной клиентской диспетчеризации).

Разделение public vs owner профиля:
- `PublicEmployeeProfile` содержит `header`, публичные контакты (только `telegram`, `workEmail` если разрешено сотрудником), `publicProjects`, `publicAchievements`, `publicStats` (без performance/bonus/personal contacts/preferences).
- `MyEmployeeProfile` содержит полный набор: `header`, `contacts` (private), `performance`, `projects`, `achievements`, `bonusGoals`, `activityFeed`, `commentsHistory`, `preferences`, `editableFields`.

Editable fields (`PATCH /api/employees/me`):
- `personalEmail`, `phone`, `telegram`, `city`, `workingHours`, `timezone`, `preferences` (частичное: `emailDigest`, `taskReminders`, `mentionsPush`, `aiSuggestions`).
- Backend должен возвращать обновлённый `MyEmployeeProfile` целиком.

Quick task:
- `CreateQuickTaskInput` = `{ title, slot: "today" | "this_week" | "later", priority?, projectId? }`;
- Результат `CreateQuickTaskResult` = `{ taskId, slot, title }`. Полный task reload выполняется через существующие `workspace tasks` endpoint-ы.

RBAC:
- `GET /api/workspace`, `GET /api/employees/me`, `PATCH /api/employees/me`, `POST /api/workspace/quick-tasks` — все авторизованные пользователи (любая `AppRole`);
- `GET /api/employees/{employee_id}` — все авторизованные пользователи компании; backend обязан самостоятельно решать, является ли запрос owner или public view, и обрезать приватные поля соответственно.

Frontend routing (для справки, в контракт не входит):
- `/app/employee/me` — alias: фронт сразу редиректит на `/app/employee/{currentUserId}` после получения `GET /api/employees/me`;
- `/app/employee/:employeeId` — единая страница, переключающаяся между owner и public видами по полю `view` из `GET /api/employees/{employee_id}`;
- `/app/building/:buildingId/floor/:floorId/employee/:employeeId` — legacy manager/admin-контекст, использует тот же endpoint.

### 5.3 Tasks

Canonical endpoints:
- `GET /api/buildings/{building_id}/floors/{floor_id}/tasks?q=&column=&priority=&employee_id=&project_id=&status=`
- `GET /api/buildings/{building_id}/floors/{floor_id}/tasks/{task_id}`
- `GET /api/buildings/{building_id}/floors/{floor_id}/tasks/{task_id}/audit`
- `GET /api/buildings/{building_id}/floors/{floor_id}/tasks/{task_id}/comments`
- `GET /api/buildings/{building_id}/floors/{floor_id}/tasks/{task_id}/checklist`
- `POST /api/buildings/{building_id}/floors/{floor_id}/tasks`
- `PATCH /api/buildings/{building_id}/floors/{floor_id}/tasks/{task_id}`
- `DELETE /api/buildings/{building_id}/floors/{floor_id}/tasks/{task_id}`
- `POST /api/buildings/{building_id}/floors/{floor_id}/tasks/{task_id}/block`
- `POST /api/buildings/{building_id}/floors/{floor_id}/tasks/{task_id}/unblock`
- `POST /api/buildings/{building_id}/floors/{floor_id}/tasks/{task_id}/deadline`
- `POST /api/buildings/{building_id}/floors/{floor_id}/tasks/{task_id}/share-link`
- `POST /api/buildings/{building_id}/floors/{floor_id}/tasks/{task_id}/comments`
- `POST /api/buildings/{building_id}/floors/{floor_id}/tasks/{task_id}/checklist`
- `PATCH /api/buildings/{building_id}/floors/{floor_id}/tasks/{task_id}/checklist/{item_id}`
- `DELETE /api/buildings/{building_id}/floors/{floor_id}/tasks/{task_id}/checklist/{item_id}`

Supported aliases:
- `GET /api/workspace/tasks?building_id={building_id}&floor_id={floor_id}&q=&column=&priority=&employee_id=&project_id=&status=`
- `GET /api/workspace/tasks/{task_id}?building_id={building_id}&floor_id={floor_id}`
- `GET /api/workspace/tasks/{task_id}/audit?building_id={building_id}&floor_id={floor_id}`
- `GET /api/workspace/tasks/{task_id}/comments?building_id={building_id}&floor_id={floor_id}`
- `GET /api/workspace/tasks/{task_id}/checklist?building_id={building_id}&floor_id={floor_id}`
- `POST /api/workspace/tasks?building_id={building_id}&floor_id={floor_id}`
- `PATCH /api/workspace/tasks/{task_id}?building_id={building_id}&floor_id={floor_id}`
- `DELETE /api/workspace/tasks/{task_id}?building_id={building_id}&floor_id={floor_id}`
- `POST /api/workspace/tasks/{task_id}/block?building_id={building_id}&floor_id={floor_id}`
- `POST /api/workspace/tasks/{task_id}/unblock?building_id={building_id}&floor_id={floor_id}`
- `POST /api/workspace/tasks/{task_id}/deadline?building_id={building_id}&floor_id={floor_id}`
- `POST /api/workspace/tasks/{task_id}/share-link?building_id={building_id}&floor_id={floor_id}`
- `POST /api/workspace/tasks/{task_id}/comments?building_id={building_id}&floor_id={floor_id}`
- `POST /api/workspace/tasks/{task_id}/checklist?building_id={building_id}&floor_id={floor_id}`
- `PATCH /api/workspace/tasks/{task_id}/checklist/{item_id}?building_id={building_id}&floor_id={floor_id}`
- `DELETE /api/workspace/tasks/{task_id}/checklist/{item_id}?building_id={building_id}&floor_id={floor_id}`

Deprecated endpoints:
- `/api/tasks`
- `/api/tasks/{task_id}`
- любые flat `/api/tasks/*` routes без `building_id` и `floor_id`

Task permission policy:
- `employee`: может работать только со своим scope; comments и checklist mutations разрешены по policy;
- `manager | company_admin | super_admin`: full task mutations в пределах scope;
- forbidden actions возвращают `403` с DRF payload.

### 5.4 Projects

Canonical endpoints:
- `GET /api/projects?q=&status=&department_id=&owner_id=&archived=`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `PATCH /api/projects/{project_id}`
- `POST /api/projects/{project_id}/archive`
- `POST /api/projects/{project_id}/restore`
- `GET /api/projects/{project_id}/members`
- `POST /api/projects/{project_id}/members`
- `PATCH /api/projects/{project_id}/members/{member_id}`
- `DELETE /api/projects/{project_id}/members/{member_id}`

Deprecated endpoints:
- `PUT /api/projects/{project_id}/members`

Project member write model:
- `POST /members` — add member
- `PATCH /members/{member_id}` — change role or membership attributes
- `DELETE /members/{member_id}` — remove member

### 5.5 Company Admin

Canonical endpoints:
- `GET /api/company/admin/overview`
- `GET /api/company/admin/organization`
- `PUT /api/company/admin/organization`
- `GET /api/company/admin/users?q=&role=&status=&department_id=`
- `GET /api/company/admin/users/{user_id}`
- `GET /api/company/admin/invites`
- `POST /api/company/admin/invites`
- `PATCH /api/company/admin/users/{user_id}/role`
- `POST /api/company/admin/users/{user_id}/block`
- `POST /api/company/admin/invites/{invite_id}/revoke`

Supported aliases:
- `/api/admin/company/overview`
- `/api/admin/company/organization`
- `/api/admin/company/users`
- `/api/admin/company/users/{user_id}`
- `/api/admin/company/invites`
- `/api/admin/company/users/{user_id}/role`
- `/api/admin/company/users/{user_id}/block`
- `/api/admin/company/invites/{invite_id}/revoke`

Deprecated terminology:
- `employees` -> use `users` as canonical resource name in admin domain
- `invitations` -> use `invites` as canonical resource name in admin domain

### 5.6 Super Admin

Canonical endpoints:
- `GET /api/admin/platform/overview`
- `GET /api/admin/platform/tenants?q=&status=`
- `GET /api/admin/platform/users`
- `GET /api/admin/platform/invites`
- `POST /api/admin/platform/tenants`
- `PATCH /api/admin/platform/tenants/{tenant_id}/status`
- `POST /api/admin/platform/invites`
- `POST /api/admin/platform/invites/{invite_id}/revoke`

Supported aliases:
- `/api/platform/admin/overview`
- `/api/platform/admin/tenants`
- `/api/platform/admin/users`
- `/api/platform/admin/invites`
- `/api/platform/admin/tenants/{tenant_id}/status`
- `/api/platform/admin/invites/{invite_id}/revoke`

### 5.7 Platform Audit

Canonical endpoints:
- `GET /api/admin/platform/audit/stats`
- `GET /api/admin/platform/audit/events?q=&tenant_id=&action=&severity=&status=&from=&to=&page=&page_size=`
- `GET /api/admin/platform/audit/export?q=&tenant_id=&action=&severity=&status=&from=&to=`

Supported aliases:
- `/api/platform/admin/audit/stats`
- `/api/platform/admin/audit/events`
- `/api/platform/admin/audit/export`

Export contract:
- `200 text/csv`
- `Content-Disposition: attachment; filename="platform-audit-YYYY-MM-DD.csv"`

### 5.8 Admin Action Center

Canonical endpoints:
- `GET /api/admin/actions/stats`
- `GET /api/admin/actions/events?q=&scope=&severity=&status=&action=&actor=&from=&to=&page=&page_size=`
- `GET /api/admin/actions/events/{action_id}`

Supported aliases:
- `/api/admin/action-center/stats`
- `/api/admin/action-center/events`
- `/api/admin/action-center/events/{action_id}`

### 5.9 Executive aggregate domain

Planned endpoints:
- `GET /api/executive/skyline`
- `GET /api/executive/buildings/{building_id}`
- `GET /api/executive/buildings/{building_id}/departments`
- `GET /api/executive/departments/{department_id}/operations`
- `GET /api/executive/employees/{employee_id}/diagnostic`
- `GET /api/executive/alerts`
- `GET /api/executive/projects/at-risk`
- `GET /api/executive/snapshots/current`

## 6. Required schema domains

### Common
- building or department status: `green | yellow | red`
- employee presence status: `online | call | vacation | sick`
- task column: `todo | in_progress | done`
- task priority: `high | medium | low`

### Projects
- project status: `active | on_hold | completed | archived`
- project member role: `owner | editor | viewer`

### Company Admin
- company user role: `employee | manager | company_admin | executive`
- company user status: `active | invited | blocked`
- company invite status: `pending | accepted | expired | revoked`

Compatibility rule for old values:
- если legacy backend еще возвращает `disabled`, frontend должен трактовать это как `blocked`;
- новый canonical enum — `blocked`.

### Super Admin
- tenant status: `active | trial | suspended`
- platform role: `platform_admin | support | security`
- platform invite status: `pending | accepted | expired | revoked`

### Audit and actions
- severity: `low | medium | high | critical`
- actor type: `user | system | integration`
- audit status: `success | failed`
- action scope: `company | platform`

## 7. Frontend compatibility rules

1. Frontend supports fallback between canonical and alias endpoints only when alias is explicitly listed here.
2. List endpoints may return:
   - plain array
   - `{ "results": [...], "count": n }`
3. CSV export must return raw `text/csv`, not JSON wrapper.
4. On `401` frontend invalidates session and redirects to login.
5. Contract changes must update this document and OpenAPI before rollout.
6. Deprecated endpoints may exist temporarily, but frontend must implement canonical routes first.

## 8. Immediate backend workstream

Primary sprint focus: **employee vertical live-integration**.

Backend team can start with:
1. Implement employee cabinet endpoints из §5.2.1:
   - `GET /api/workspace`
   - `GET /api/employees/me`
   - `GET /api/employees/{employee_id}` (owner/public split)
   - `PATCH /api/employees/me`
   - `POST /api/workspace/quick-tasks`
2. Follow task-ready plan from `docs/backend/EMPLOYEE_BACKEND_WORKSTREAM.md`.
3. Publish `/schema/`, Swagger and ReDoc for implemented endpoints.
4. Provide minimal dev seed data for colleague/public-profile checks.
5. Delivery checklist:
   - base URL
   - test credentials for roles `employee | manager | company_admin`
   - known limitations or incomplete endpoints
