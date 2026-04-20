# OpenAPI Release Gate

Дата: 2026-04-16
Статус: единый release gate для backend/frontend интеграции

## 1) Назначение

Этот документ нужен как единый checklist перед handoff и перед live-подключением frontend.
Он заменяет разрозненные openapi/checklist/lock документы.

## 2) OpenAPI coverage

Проверьте, что `/schema/` покрывает все домены из `docs/backend/BACKEND_HANDOFF.md`:
- auth/session
- buildings / departments / workspace / employee profile
- tasks
- projects
- company admin
- super admin
- platform audit
- admin action center
- executive aggregate domain, если он уже вошел в этап реализации

## 3) Schema rules

Обязательные правила:
1. Path params (`building_id`, `floor_id`, `employee_id`, `task_id`, `project_id`, и т.д.) заданы явно и типизированы.
2. Query params для list/filter routes отражены в схеме.
3. Все enum-поля описаны как enum, а не как свободные string.
4. Nullable поля помечены явно.
5. Для дат используется `date-time` или `date`, где это применимо.
6. Ошибки документированы как DRF payload `{ "detail": "..." }`.

## 4) Response format rules

Допустимые list форматы:
- plain array
- `{ "results": [...], "count": n }`

Целевой list формат:

```json
{ "count": 0, "results": [] }
```

CSV export:
- content type: `text/csv`
- корректный `Content-Disposition`

## 5) Contract checks by domain

### 5.1 Workspace / org
- `Building` schema содержит ключевые поля summary
- department schemas содержат staffing/risk fields
- workspace schema содержит `zones` и `employees`
- employee profile schema содержит `projects`, `activity_feed`, `comments_history`, `performance`

### 5.2 Tasks
- list/details/audit/comments/checklist отражены в OpenAPI
- checklist item содержит `id`, `title`, `done`, `position`
- comments create request содержит `message`
- permissions для forbidden mutations отдаются через `403`

### 5.3 Projects
- CRUD и members endpoints отражены
- project/member enums совпадают с frontend expectations

### 5.4 Company Admin / Super Admin
- users/invites/role/status endpoints отражены
- invite and role enums зафиксированы
- cross-company/platform scopes не смешаны

### 5.5 Platform Audit / Action Center
- filters отражены как query params
- details endpoints описаны
- CSV export описан отдельно

### 5.6 Executive domain
- aggregate schemas отделены от raw employee operational schemas
- skyline/building/department/employee diagnostic endpoints имеют свои response models

## 6) Manual smoke gate

Перед sign-off пройти:
1. `VITE_API_SOURCE=live`
2. `VITE_API_MOCK_FALLBACK=false`
3. сценарий:
   - login
   - workspace
   - tasks
   - projects
   - company admin
   - action center
   - super admin
   - audit
   - executive, если домен уже реализован

Проверить:
- `200/201/204` на happy-path
- `403` на forbidden paths
- `404` на missing entities
- валидный JSON или CSV без ручных хотфиксов на frontend

## 7) Release gate (must pass)

1. `/schema/`, Swagger, ReDoc открываются без ошибок.
2. Все обязательные endpoint-ы присутствуют в OpenAPI.
3. Примеры payload используют целевой `snake_case`.
4. Enum domains совпадают с frontend expectations.
5. Smoke в live-режиме проходит без mock fallback.
6. Любые изменения контракта отражены в `docs/backend/BACKEND_HANDOFF.md`.
