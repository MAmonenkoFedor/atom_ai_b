# Backend: что нужно сейчас (Employee vertical)

Дата: 2026-04-20  
Статус: единая точка входа для backend-команды по текущему спринту

## Назначение

Этот файл — **короткий handoff «отправить в чат бэку»**: статус интеграции, открытые вопросы и критерии готовности. Детальный API-контракт по полям и путям остаётся в `docs/backend/BACKEND_HANDOFF.md` (§5.2.1 и связанные разделы).

Сопутствующие документы (канон, без дублей):

| Документ | Зачем |
|----------|--------|
| `docs/backend/BACKEND_HANDOFF.md` | Канонические пути, alias, схемы, ошибки |
| `docs/backend/LIVE_CONNECTION_GUIDE.md` | Env, креды, CSRF, smoke-чеклист, примеры payload |
| `docs/backend/FRONTEND_BACKEND_SYNC_PROTOCOL.md` | Как передавать изменения API и сигнал готовности endpoint |
| `backend/FRONTEND_DELIVERY_V1.md` | Готовый v1 пакет для пересылки frontend-команде |

## Цель спринта

Закрыть live-контур сотрудника для маршрутов:

- `/app/workspace`
- `/app/employee/me`
- `/app/employee/:employeeId`

Фронт шлёт write-запросы в **snake_case** и нормализует ответы в `camelCase` на своей стороне.

## P0 endpoints (порядок реализации)

1. `GET /api/workspace`
2. `GET /api/employees/me`
3. `GET /api/employees/{employee_id}` — owner vs `view: "public"` по правилу «свой id → owner, иначе public» без утечки приватных полей
4. `PATCH /api/employees/me` — частичный patch, ответ = полный актуальный owner-профиль
5. `POST /api/workspace/quick-tasks` — `title`, `slot` (`today | this_week | later`), опционально `priority`, `project_id`; ответ с `task_id`, `slot`, `title`

Детали полей и примеры — в `BACKEND_HANDOFF.md` и в `LIVE_CONNECTION_GUIDE.md`.

## Статус live (последняя проверка)

Уже **200/201** в связке с фронтом:

- `POST /api/auth/login` → `200`
- `GET /api/workspace` → `200`
- `GET /api/employees/me` → `200`
- `GET /api/employees/emp-2` → `200` (`view=public`)
- `PATCH /api/employees/me` → `200`
- `POST /api/workspace/quick-tasks` → `201`

## Что уже сделано на фронте

- Live auth (`/api/auth/login` + `/api/auth/session`), cookie session по умолчанию
- CSRF для write: cookie `csrftoken`, заголовок `X-CSRFToken`, `Referer` (см. live guide)
- Маппинг snake_case для patch/quick-task
- Нормализаторы под owner/public, `editableFields`, `header` (title/status и т.д.)

## Открытые вопросы (нужно согласовать с backend)

1. **Кодировка / локаль** текстовых полей в `workspace` (greeting и др.) — единый подход (UTF-8 + язык стенда).
2. **Канон роли в профиле**: `header.role` vs `header.title` — один source-of-truth; при наличии обоих — явно зафиксировать в OpenAPI и changelog.
3. **Timestamps** — ISO-8601 везде или согласованные display-строки; не смешивать без пометки в схеме.

После согласования — обновить OpenAPI и `BACKEND_HANDOFF.md`, короткий блок по формату из `FRONTEND_BACKEND_SYNC_PROTOCOL.md`.

## Seed / demo data для smoke

- Роли: как минимум `employee`, `manager`, `company_admin`
- Не меньше **3** сотрудников в одной компании (public-профиль коллеги)
- Задачи по группам: `overdue`, `today`, `this_week`, `later`, `done`
- Минимум один activity item с **`actor`** (переход на профиль коллеги)

## Definition of done (backend → frontend)

1. Пять P0 endpoint-ов со стабильным контрактом и JSON-ошибками (не HTML).
2. Фронт в `VITE_API_SOURCE=live` и `VITE_API_MOCK_FALLBACK=false` проходит smoke из `LIVE_CONNECTION_GUIDE.md`.
3. OpenAPI соответствует `BACKEND_HANDOFF.md`.

## Следующий шаг для backend-команды

1. Закрыть alignment по трём открытым вопросам выше.
2. Отправить в чат **readiness signal** по каждому изменённому endpoint (шаблон в `FRONTEND_BACKEND_SYNC_PROTOCOL.md`).
3. Совместный UI smoke: `employee_test` → workspace → owner/public profile → patch → quick task.
