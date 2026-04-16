# ATOM AI Backend - Отчет О Выполненных Работах

Дата обновления: 2026-04-14

## 1. Что уже реализовано

### 1.1 Platform Foundation (Phase 0)

- Поднят backend skeleton на Django + DRF.
- Добавлены settings-профили:
  - `config.settings.local`
  - `config.settings.stage`
  - `config.settings.prod`
- Подключена инфраструктура через `docker-compose`:
  - PostgreSQL
  - Redis
  - MinIO
- Подключены Celery-настройки и базовый `config/celery.py`.
- Добавлены health endpoint’ы:
  - `GET /health/live/`
  - `GET /health/ready/`
- Подключены OpenAPI schema и Swagger:
  - `GET /api/schema/`
  - `GET /api/docs/`
- Добавлены:
  - единый pagination format
  - единый error handler
- Подготовлен bootstrap-скрипт:
  - `scripts/bootstrap.ps1`

### 1.2 Identity + Organization + Hierarchy (Phase 1)

Реализованы домены:

- `identity`
  - `Role`
  - `UserRole`
- `organizations`
  - `Organization`
  - `OrganizationMember`
- `orgstructure`
  - `OrgUnit`
  - `OrgUnitMember`
  - `UserManagerLink`

Реализованы endpoint’ы:

- `GET /api/v1/me`
- `GET /api/v1/employees`
- `GET /api/v1/employees/{id}`
- `GET /api/v1/org/units`
- `GET /api/v1/org/units/{id}`
- `GET /api/v1/org/units/{id}/children`
- `GET /api/v1/org/units/{id}/members`

### 1.3 Projects + Chats + AI Run Skeleton (Phase 2)

Реализованы домены:

- `projects`
  - `Project`
  - `ProjectMember`
- `chats`
  - `Chat`
  - `ChatMember`
  - `Message`
- `ai`
  - `AiRun`

Реализованы endpoint’ы:

- `GET /api/v1/projects`
- `POST /api/v1/projects`
- `GET /api/v1/projects/{id}`
- `GET /api/v1/projects/{id}/members`
- `GET /api/v1/chats`
- `POST /api/v1/chats`
- `GET /api/v1/chats/{id}`
- `GET /api/v1/chats/{id}/messages`
- `POST /api/v1/chats/{id}/messages`
- `POST /api/v1/ai/runs`
- `GET /api/v1/ai/runs/{id}`

### 1.4 LLM Gateway v1 (Phase 3)

Добавлен домен `llm_gateway`:

- `LlmProvider`
- `LlmModel`
- `LlmModelProfile`
- `LlmRequestLog`

Реализовано:

- Роутинг по profile/provider/model.
- Seed профилей моделей:
  - `chat_fast`
  - `chat_balanced`
  - `chat_deep`
  - `summary_fast`
  - `summary_batch`
- Retry/fallback policy:
  - `LLM_GATEWAY_MAX_RETRIES`
  - `LLM_GATEWAY_ENABLE_FALLBACK`
  - `LLM_GATEWAY_TIMEOUT_MS`
- Execute endpoint:
  - `POST /api/v1/ai/runs/{id}/execute`
- Логирование каждой попытки выполнения в `LlmRequestLog`.
- Endpoint логов AI-run:
  - `GET /api/v1/ai/runs/{id}/logs`
- Поддержаны фильтры логов:
  - `status`, `provider`, `limit`
  - `sort` (`created_at|latency_ms|total_tokens` c `-` для DESC)
  - `from`, `to` (ISO datetime или `YYYY-MM-DD`)
  - `has_error` (`true/false`, `1/0`, `yes/no`)
  - `min_latency_ms` (целое неотрицательное число)

Поддерживаются режимы адаптеров:

- Mock mode (по умолчанию)
  - `LLM_GATEWAY_MOCK_MODE=True`
- Real provider mode
  - OpenAI
  - Anthropic Claude
  - Gemini

## 2. Реализация контракта от Frontend-команды

Реализован отдельный read-only модуль `workspaces`, совместимый с frontend-документом:

- `GET /api/buildings`
- `GET /api/buildings/{building_id}`
- `GET /api/buildings/{building_id}/departments`
- `GET /api/buildings/{building_id}/floors/{floor_id}/workspace`
- `GET /api/buildings/{building_id}/floors/{floor_id}/workspace/employee/{employee_id}`
- `GET /api/buildings/{building_id}/floors/{floor_id}/employees/{employee_id}/profile`

Поддержаны alias endpoint’ы:

- `GET /api/buildings/{building_id}/floors/{floor_id}/workspace-context?employee_id={employee_id}`
- `GET /api/workspace/context?building_id={building_id}&floor_id={floor_id}&employee_id={employee_id}`
- `GET /api/employees/{employee_id}/profile?building_id={building_id}&floor_id={floor_id}`

Подключены оба варианта base URL:

- `/api/v1/...`
- `/api/...`

## 3. Текущий статус проверок

- Выполнялись `python manage.py check` после ключевых этапов.
- Миграции для реализованных доменов сгенерированы и применены:
  - `identity`
  - `organizations`
  - `orgstructure`
  - `projects`
  - `chats`
  - `ai`
  - `llm_gateway`
- Smoke-проверки endpoint’ов выполнялись через реальные HTTP-запросы к локальному серверу.
- Отдельно проверен `GET /api/v1/ai/runs/{id}/logs`:
  - `?has_error=true` -> `200`
  - `?has_error=false` -> `200`
  - `?min_latency_ms=100` -> `200`
  - `?has_error=maybe` -> `400` (валидация)
  - `?min_latency_ms=-1` -> `400` (валидация)

## 4. Известные моменты

- Сейчас глобально включен unified error handler, поэтому формат ошибок возвращается в обертке `{"error": ...}`.
- В документе frontend указано ожидание DRF-стиля `{ "detail": "..." }`.
- При необходимости можно:
  - отключить общий exception handler, или
  - сделать bypass для `workspaces` endpoint’ов.

## 5. Что логично делать следующим шагом

1. Привести error contract к точному frontend-ожиданию (`detail`) для согласованных endpoint’ов.
2. Добавить кэш (30-120 сек) на workspace/profile агрегаты.
3. Подготовить интеграцию реальных источников данных вместо текущих mock-данных в `workspaces/data.py`.
4. Добавить минимальный integration test suite для критичных контрактных endpoint’ов.

## 6. Обновление от 2026-04-15 (Parallel Contract v2)

По документу `API_BACKEND_PARALLEL_REQUESTS_v2.md` добавлено:

- Auth/session endpoint’ы:
  - `POST /api/auth/login`
  - `POST /api/auth/logout`
  - `GET /api/auth/session`
  - `POST /api/auth/invite/activate`
- Расширен Projects API:
  - `PATCH /api/projects/{project_id}`
  - `POST /api/projects/{project_id}/archive`
  - `POST /api/projects/{project_id}/restore`
  - `POST /api/projects/{project_id}/members`
  - `PATCH /api/projects/{project_id}/members/{member_id}`
  - `DELETE /api/projects/{project_id}/members/{member_id}`
  - фильтры: `q`, `status`, `owner_id`, `department_id`
- Добавлены Company Admin endpoint’ы (primary + alias):
  - `overview`, `departments`, `users`, `invites`, `role update`, `invite revoke`
- Добавлены Super Admin endpoint’ы (primary + alias):
  - `overview`, `tenants`, `users`, `invites`, `tenant status`, `invite revoke`
- Добавлены Platform Audit endpoint’ы (primary + alias):
  - `stats`, `events`, `export` (`text/csv`, `Content-Disposition`)
- Добавлены Admin Action Center endpoint’ы (primary + alias):
  - `GET /api/admin/actions/stats`
  - `GET /api/admin/actions/events`
  - `GET /api/admin/actions/events/{action_id}`
  - `GET /api/admin/action-center/stats`
  - `GET /api/admin/action-center/events`
  - `GET /api/admin/action-center/events/{action_id}`

Технически:

- `python manage.py check` проходит без ошибок.
- Линтер-диагностика по измененным файлам чистая.
- Полный HTTP smoke по новым endpoint’ам нужно повторить после поднятия PostgreSQL (сейчас `OperationalError: connection timeout localhost:5433`).
- Для parallel contract endpoint’ов добавлены OpenAPI-аннотации:
  - явные `operationId`
  - query params в schema
  - request/response serializers для read/write операций
  - корректные `404` через `NotFound` (вместо `ValidationError` с кодом)
