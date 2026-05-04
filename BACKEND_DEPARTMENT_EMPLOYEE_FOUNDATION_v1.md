# Backend Delivery: Department & Employee Foundation v1

Дата: 2026-05-04  
Статус: **Done, runtime-confirmed (`91 → 99 → 106 tests OK`)**  
Базовый URL: `/api/v1`  
Auth: Bearer JWT (как раньше)  
Аудитория документа: PM, frontend lead, руководство

---

## 1. TL;DR (для руководства)

В этом релизе закрыты два полноценных доменных уровня платформы:

1. **Department Workspace** — отдел как самостоятельная сущность: чтение, редактирование, состав, проекты, документы.
2. **Employee Profile / Workspace foundation** — сотрудник как отдельный навигационный узел: профиль, отделы сотрудника, его проекты, его workspace.

Оба домена построены на едином **policy/access слое** (`PolicyDecision`, `resolve_access`) — тот же стандарт, что у проектов и AI workspace. На каждое чувствительное действие пишется **audit event**. Все изменения покрыты тестами и проходят полный прогон.

```text
Company
  → Departments         ← закрыт (read / patch / members / docs / workspace / audit)
    → Employees         ← закрыт foundation + managed (read / patch / roles / permissions / workspace / audit)
      → Personal AI Workspace
      → Projects
      → Documents
      → Roles / Permissions   (done)
```

Бэкенд готов к UI-проработке: контракты стабильные, права формализованы, audit trail есть.

---

## 2. Что уже было до этого блока (контекст)

Эти куски бэкенда уже жили в проде/стейдже и упоминаются для полноты контекста (UI на них уже опирается):

- `POST /api/auth/login`, `GET /api/employees/me`, `GET /api/workspace`, `POST /api/workspace/quick-tasks` — см. `backend/FRONTEND_DELIVERY_V1.md`.
- Project workspace, project documents, project members — `apps/projects/api/views.py`.
- Access/role model: `PermissionDefinition`, `PermissionGrant`, `RoleTemplate`, `DelegationRule`, `PermissionDeny`, `RoleTemplateAssignment` — `apps/access/models.py`.
- Базовые admin-эндпоинты для отделов: `/api/company/admin/departments`, `/api/company/admin/departments/<id>`, `/api/company/admin/departments/<id>/lead` — `apps/orgstructure/api/company_admin_departments.py`.
- AI workspace privacy: `ai.workspace.view_metadata` / `ai.workspace.view_content` (metadata-by-default).

---

## 3. Что добавлено в этом релизе

### 3.1 Department Workspace endpoints

Все маршруты — `IsAuthenticated`, права проверяются через `resolve_access(scope_type="department")`.

| Метод | URL | Что делает | Право | Audit event |
|---|---|---|---|---|
| `GET`    | `/api/v1/departments` | Список отделов, видимых пользователю; в каждой строке `access_level` | `department.read` или `department.view_metadata` | — |
| `GET`    | `/api/v1/departments/<id>` | Карточка отдела (description маскируется в metadata-only) | `department.read` или `department.view_metadata` | — |
| `PATCH`  | `/api/v1/departments/<id>` | Частичное обновление: `name`, `code`, `description`, `parent_id`, `is_active` | `department.update` | `department.updated` |
| `GET`    | `/api/v1/departments/<id>/workspace` | Workspace-дескриптор + `links` (employees / projects / documents) | `department.read` или `department.view_metadata` | — |
| `GET`    | `/api/v1/departments/<id>/employees` | Состав отдела | `department.read` | `department.employees_listed` |
| `POST`   | `/api/v1/departments/<id>/employees` | Добавить сотрудника (`user_id`, `position`, `is_lead`) | `department.manage_members` | `department.employee_added` |
| `DELETE` | `/api/v1/departments/<id>/employees/<employee_id>` | Удалить сотрудника (по `user_id`) | `department.manage_members` | `department.employee_removed` |
| `GET`    | `/api/v1/departments/<id>/projects` | Проекты, у которых `primary_org_unit = <id>` | `department.read` | `department.projects_listed` |
| `GET`    | `/api/v1/departments/<id>/documents` | Документы отдела (`OrgUnitDocument`) | `document.read` или `document.view_metadata` (department-scope) | `department.document_metadata_accessed` / `department.document_content_accessed` |
| `POST`   | `/api/v1/departments/<id>/documents/upload` | Загрузка файла (multipart, `file`) | `document.upload` или `department.manage_documents` | `department.document_uploaded` |
| `POST`   | `/api/v1/departments/<id>/documents/link` | Внешняя ссылка (`title`, `url`) | `document.share` или `department.manage_documents` | `department.document_linked` |

#### 3.1.1 Поведение и инварианты PATCH/POST/DELETE

- Уникальность `name` отдела внутри организации.
- `parent_id` — только в пределах той же организации, **без циклов** в дереве отделов.
- При добавлении сотрудника проверяется активное `OrganizationMember`.
- При смене главы отдела (`is_lead=true`) у предыдущего главы автоматически отзываются scoped-гранты (`_revoke_dept_lead_scoped_grants`).
- При удалении главы — то же самое + `remove_from_department` пишет события в `EmployeeCareerEvent`.
- Документы:
  - Аудит зависит от того, есть ли в выдаче хотя бы один непустой `href` (для metadata-only пользователей `href` маскируется в пустую строку).
  - Поддерживаются загрузка в S3/MinIO через `StorageProvider` или fallback на `FileField` (FS).
  - Допустимые расширения и лимит `15 MB` — как у проектных документов.

#### 3.1.2 Контракт PolicyDecision (общий)

Возвращается единый объект, который фронт может **использовать для управления UI** (включать/отключать кнопки, прятать поля):

```json
{
  "allowed": true,
  "access_level": "metadata | read | write | manage | admin",
  "reason": "department_membership | permission:... | privileged_company_role | ...",
  "scope_type": "department",
  "scope_id": "12",
  "subject_id": 7,
  "object_id": 12
}
```

Уровни → действия:

```text
metadata → видно карточку, без чувствительных полей
read     → можно открывать содержимое
write    → PATCH/POST/DELETE на полях / составе
manage   → плюс роли/документы/конфигурация workspace
admin    → суперпользователь / company-wide privileged
```

---

### 3.2 Employee Profile / Workspace endpoints

Новый домен `/api/v1/employees/*`. Все права через `resolve_access(scope_type="employee")`.

| Метод | URL | Что делает | Право | Audit event |
|---|---|---|---|---|
| `GET` | `/api/v1/employees` | Список сотрудников, видимых пользователю; per-row `access_level` | `employee.view_metadata` или `employee.read` | `employee.listed` |
| `GET` | `/api/v1/employees/<user_id>` | Карточка сотрудника (поля `email/first_name/last_name/job_title` маскируются в metadata-only) | `employee.view_metadata` или `employee.read` | `employee.metadata_accessed` / `employee.content_accessed` |
| `GET` | `/api/v1/employees/<user_id>/departments` | Отделы сотрудника | `employee.read` | `employee.departments_listed` |
| `GET` | `/api/v1/employees/<user_id>/projects` | Проекты сотрудника | `employee.read` | `employee.projects_listed` |
| `GET` | `/api/v1/employees/<user_id>/workspace` | Workspace-дескриптор сотрудника + `links` | `employee.view_workspace_metadata` или `employee.view_workspace_content` | `employee.workspace_metadata_accessed` / `employee.workspace_content_accessed` |

#### 3.2.1 Видимость списка сотрудников

`apply_employee_list_visibility` ограничивает результат до:

- самого пользователя;
- сотрудников **общих организаций** + либо привилегированная роль (`admin`/`company_admin`/`super_admin`/`executive`/`ceo`), либо общий отдел, либо явный `PermissionGrant` со scope `employee:<id>`.

#### 3.2.2 Workspace metadata vs content

`employee.view_workspace_metadata` — раскрывает ссылки навигации без секретов.  
`employee.view_workspace_content` — открывает в `links` ещё и `personal_workspace`.

Это совместимо с уже существующей моделью AI workspace (metadata by default).

---

### 3.2.3 Employee managed-level (добавлено после foundation)

Дополнительно закрыт write-контур сотрудника:

| Метод | URL | Что делает | Право | Audit event |
|---|---|---|---|---|
| `PATCH` | `/api/v1/employees/<user_id>` | Обновляет `first_name`, `last_name`, `email`, `job_title` (через career service) | `employee.update` | `employee.updated` |
| `GET` | `/api/v1/employees/<user_id>/roles` | Текущая system role сотрудника | `employee.read` | — |
| `PUT` | `/api/v1/employees/<user_id>/roles` | Смена `system_role` (через `change_system_role`) | `employee.manage_roles` | `employee.role_updated` |
| `GET` | `/api/v1/employees/<user_id>/permissions` | Список grant-ов сотрудника | `employee.read` | — |
| `POST` | `/api/v1/employees/<user_id>/permissions` | Выдача permission grant (`scope_type/scope_id/grant_mode/expires_at`) | `employee.manage_roles` | `employee.permission_granted` |
| `POST` | `/api/v1/employees/<user_id>/permissions/<grant_id>/revoke` | Отзыв гранта | `employee.manage_roles` | `employee.permission_revoked` |

Ключевые детали:

- `PATCH` по `job_title` пишет карьерное событие через `change_job_title`, а не «молча» меняет поле.
- `PUT /roles` использует `change_system_role` (с защитой CEO/super_admin).
- для `scope_type=\"employee\"` в выдаче прав `scope_id` принудительно должен совпадать с целевым `user_id`.
- сервис прав использует `apps.access.service.grant_permission/revoke_permission`, поэтому сохраняется единый permission audit trail + каскадный revoke delegated grants.

### 3.3 Расширение access-каталога

Файл: `apps/access/seed.py`.

**Новые permission codes:**

- Department (workspace foundation): `department.view_metadata`, `department.read`, `department.update`, `department.manage_members`, `department.manage_workspace`, `department.manage_documents`, `department.view_reports`, `department.use_ai`.
- Employee foundation: `employee.view_metadata`, `employee.read`, `employee.update`, `employee.manage_roles`, `employee.view_workspace_metadata`, `employee.view_workspace_content`.
- Унифицированный документный контракт (там, где раньше были только `docs.*`): `document.view_metadata`, `document.read`, `document.upload`, `document.update`, `document.delete`, `document.share`.

**Новые role bundles:**

- `department_coordinator_base` — кратко: координатор отдела (read/manage workspace/manage documents/manage members).

**Новые `DelegationRule`:**

- `company → department` для всех `department.*` foundation-прав.
- `company → department` и `department → employee` для `document.*` (метаданные/чтение/загрузка/шаринг/обновление).
- `company/department → employee` для `employee.*` (включая `view_workspace_metadata` и `view_workspace_content`).

**Изменения в моделях access (миграция `access/0003_scope_employee.py`):**

- Добавлен `SCOPE_EMPLOYEE = "employee"` в `SCOPE_CHOICES` и `SCOPE_BREADTH_ORDER`.
- `PermissionGrant`, `PermissionDeny`, `RoleTemplate`, `RoleTemplateAssignment`, `DelegationRule` — `scope_type` обновлён до новых choices (без потери данных).

---

### 3.4 Policy слой и helpers

| Файл | Что добавлено |
|---|---|
| `apps/access/policies.py` | `_resolve_department_action`, `_resolve_employee_action`, `_resolve_department_document_base`, `_normalize_document_resource` (теперь возвращает 5-tuple), `_coerce_employee_resource`, ветка `scope_type="employee"` в `resolve_access` |
| `apps/orgstructure/department_permissions.py` | `compute_department_policy_decision`, `apply_department_list_visibility`, `require_view_department`, `require_department_access`, `has_department_access_permission`, `can_manage_department` |
| `apps/orgstructure/employee_permissions.py` | `compute_employee_policy_decision`, `apply_employee_list_visibility`, `has_employee_scoped_permission`, `shared_org_ids`, `shared_department_ids`, `is_privileged_employee_viewer` |
| `apps/orgstructure/department_documents.py` | `list_department_documents`, `create_department_document_link`, `create_department_document_upload` (с тем же контрактом, что у `project_documents`) |
| `apps/orgstructure/models.py` | `OrgUnitDocument` (file/external link, `to_api_dict`, `resolve_href` через S3 / FS), `org_unit_document_upload_to` |

Все ladder-ы решений (membership → role → permission → metadata) написаны идентично проектным — фронту не нужно учить два разных набора правил.

---

### 3.5 Audit events (полный список новых)

Можно подписывать дашборды и алерты:

```text
department.updated
department.employees_listed
department.employee_added
department.employee_removed
department.projects_listed
department.document_metadata_accessed
department.document_content_accessed
department.document_uploaded
department.document_linked

employee.listed
employee.metadata_accessed
employee.content_accessed
employee.departments_listed
employee.projects_listed
employee.workspace_metadata_accessed
employee.workspace_content_accessed
employee.updated
employee.role_updated
employee.permission_granted
employee.permission_revoked
```

В payload каждого события — `policy_audit_payload(d)` (`access_level`, `reason`, `scope_type`, `scope_id`) + контекстные ключи (`department_id`, `employee_id`, `count`, `fields`, `title`, `type`).

---

## 4. Что нужно от фронтенда (для PM → frontend lead)

### 4.1 Новые экраны / навигация

1. **Department workspace**:
   - Карточка отдела (`GET /departments/<id>`).
   - Вкладка «Сотрудники» (`/departments/<id>/employees`) с действиями «Добавить» (`POST`) и «Удалить» (`DELETE …/<employee_id>`).
   - Вкладка «Проекты» (`/departments/<id>/projects`).
   - Вкладка «Документы» (`/departments/<id>/documents`) с двумя кнопками: загрузка файла и добавление ссылки.
   - Кнопка «Редактировать отдел» (`PATCH …/<id>`).

2. **Employee profile**:
   - Карточка сотрудника (`/employees/<user_id>`).
   - Вкладки «Отделы» / «Проекты» / «Workspace».
   - В списке сотрудников (`GET /employees`) использовать поле `access_level` для решения, открывать ли карточку как metadata-only превью или как полную.

### 4.2 UI rules от PolicyDecision

Каждый ответ детальных эндпоинтов содержит `access_level`. Это **главный сигнал**, на который должен опираться UI:

```text
metadata  →  показывать только публичные поля; кнопки PATCH / DELETE / Add — disabled;
             в выдаче документов href = "" (это валидно, не считать ошибкой)
read      →  показывать содержимое, скрывать write-кнопки
write     →  включать «редактировать», «загрузить документ», «удалить участника»
manage    →  включать управление документами и составом
admin     →  всё включено
```

`reason` стоит логировать в frontend-консоль/Sentry — он помогает диагностировать «почему не пускает».

### 4.3 Mass-data контракт

- Списки возвращают **массив**, не пагинированный объект (для согласованности с `projects-list`/`departments-list`).
- Все `id` — числовые (`int`), кроме legacy `/api/employees/<employee_id>` из `apps/workspaces` (там строковые `emp-*`). Новый `/api/v1/employees/<user_id>` использует именно `user_id` (int).

### 4.4 Ошибки

| Код | Когда | Что показывать |
|---|---|---|
| `200/201/204` | OK | — |
| `400` | Невалидное тело (`name` пустой, `parent_id` не из той же организации, `user_id` не в организации, файл слишком большой/неподдерживаемый) | Сообщение из `detail` / поля сериализатора |
| `403` | `resolve_access` вернул `allowed=false` | «Недостаточно прав» + при желании reason из ответа |
| `404` | Объект не виден из-за `apply_*_list_visibility` или его правда нет | «Не найдено» — намеренно одинаково для не-видных и не-существующих |

### 4.5 Backwards-compat

- Эндпоинты `/api/employees/me`, `/api/employees/<emp_id>`, `/api/workspace`, `/api/workspace/quick-tasks` **не тронуты** — UI можно мигрировать постепенно.
- `/api/company/admin/departments*` остаётся для super/company admin интерфейса; новый `/api/v1/departments/<id>` — **рабочий контур** (member/lead/coord), а не админ-страница.

---

## 5. Тесты и качество

| Категория | Файл | Что покрыто |
|---|---|---|
| Department API | `apps/orgstructure/tests/test_department_workspace_api.py` | list/detail/workspace/employees/projects/documents (метаданные vs контент)/PATCH/POST member/DELETE member |
| Department policies | `apps/access/tests/test_department_policies.py` | ladder для `department.read` / `department.update` / `department.manage_*` |
| Document policies | `apps/access/tests/test_document_policies.py` | project/workspace/department branches; metadata vs content split |
| Employee API | `apps/orgstructure/tests/test_employee_workspace_api.py` | видимость списка, маскирование metadata-only, `403` без `employee.read`, workspace metadata audit |
| Employee policies | `apps/access/tests/test_employee_policies.py` | self-read, invalid scope, явная workspace-permission ветка |

**Результат:** `python manage.py test --verbosity=0` → **99 tests, OK** (с включённым privacy gate в CI).

---

## 6. Что **не** входило в этот релиз (next-up предложения)

Это уже про следующий PR, не про этот:

1. `GET /api/v1/employees/<user_id>/audit` — лента карьерных событий + чувствительных audit events для одного сотрудника.
2. Role templates в employee-контуре (`/employees/<id>/templates`) поверх уже существующих `/api/v1/access/*`.
3. Tasks domain (`/api/v1/tasks/*`) — отложен; после закрытия employee managed-level.
4. Frontend live-сверка (smoke matrix) — расширить `scripts/access_http_matrix_smoke.py` под новые employee write маршруты.

---

## 7. Mini-changelog (для отчёта руководству)

```text
+ Department Workspace foundation (5 GET endpoints, audit, policy)
+ Department Documents (list / upload / link, metadata/content split)
+ Department PATCH + members management (employee_added / employee_removed audit)
+ Employee Profile foundation (5 GET endpoints, metadata/read split, workspace metadata vs content)
+ Employee managed-level (PATCH profile, PUT roles, POST/REVOKE permission grants)
+ Access catalog: 5 new department perms, 6 new employee perms, unified document.* contract
+ Delegation rules: company→department for department.*; company/department→employee for employee.*
+ New scope: SCOPE_EMPLOYEE (migration access/0003)
+ Policy contract: resolve_access(scope_type in {department, employee, document, ...})
+ +106 tests (full suite green)
```

---

## 8. Контакты

- Backend lead: текущий канал (этот тред).
- Документ обновляется при каждом merge'е следующего домена (`employees write/manage` → следующий v2 этого packet'а).
