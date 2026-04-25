# Frontend Live Connection Guide

Дата: 2026-04-17
Статус: готово к использованию frontend-командой

## 1) Base URL и документация

- Backend base URL: `http://127.0.0.1:8000/api`
- Swagger UI: `http://127.0.0.1:8000/api/docs/`
- OpenAPI JSON: `http://127.0.0.1:8000/api/schema/`
- Alignment Swagger: `http://127.0.0.1:8000/api/alignment/docs/`
- Alignment schema: `http://127.0.0.1:8000/api/alignment/schema/`

## 2) Frontend env (обязательный baseline)

```env
VITE_API_SOURCE=live
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_API_PREFIX=/api
VITE_API_MOCK_FALLBACK=false
VITE_API_MOCK_LATENCY_MS=120
```

Пояснения:

- `VITE_API_MOCK_FALLBACK=false` обязателен для честного live smoke.
- Если нужен временный fallback для локальной разработки, можно поставить `true`, но это невалидно для integration smoke.

## 3) Тестовые креды

- `employee_test / AtomTest123!`
- `manager_test / AtomTest123!`
- `company_admin_test / AtomTest123!`
- `super_admin_test / AtomTest123!`

## 4) Employee vertical endpoints

P0 endpoints:

1. `GET /api/workspace`
2. `GET /api/employees/me`
3. `GET /api/employees/{employee_id}`
4. `PATCH /api/employees/me`
5. `POST /api/workspace/quick-tasks`

## 5) Auth/CSRF для write запросов

Backend использует session-auth + CSRF.

Для `PATCH/POST/PUT/DELETE` обязательно передавать:

- cookie `csrftoken`
- header `X-CSRFToken: <csrftoken>`
- header `Referer: http://127.0.0.1:8000/`

## 6) Минимальный live smoke (frontend checklist)

1. Логин:
   - `POST /api/auth/login`
2. Workspace:
   - `GET /api/workspace` -> `200`
3. Owner profile:
   - `GET /api/employees/me` -> `200`
4. Public colleague profile:
   - `GET /api/employees/emp-2` -> `200` и `view=public`
5. Patch owner profile:
   - `PATCH /api/employees/me` -> `200`
6. Quick task:
   - `POST /api/workspace/quick-tasks` -> `201`

## 7) Пример payload для PATCH /api/employees/me

```json
{
  "city": "Moscow",
  "preferences": {
    "ai_suggestions": true
  }
}
```

## 8) Пример payload для POST /api/workspace/quick-tasks

```json
{
  "title": "Frontend live smoke quick task",
  "slot": "today",
  "priority": "high",
  "project_id": "pr-1"
}
```

## 9) Что делать при ошибках

- `401`: проверить, что есть активная session cookie после логина.
- `403`: проверить CSRF (`csrftoken`, `X-CSRFToken`, `Referer`).
- `404`: сверить endpoint с `BACKEND_HANDOFF.md` (канонические пути).
- `400`: посмотреть DRF detail/field errors в response body.

## 10) Процесс синхронизации изменений

- Обязательный формат передачи изменений backend -> frontend:
  - `FRONTEND_BACKEND_SYNC_PROTOCOL.md`
- Канонический контракт:
  - `BACKEND_HANDOFF.md`
