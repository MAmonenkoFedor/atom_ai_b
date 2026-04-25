# Live connection (frontend ↔ backend)

Дата: 2026-04-20  
Статус: операционный гайд для локальной и стендовой интеграции

## 1) Base URL и документация

- Backend base URL: `http://127.0.0.1:8000/api`
- Swagger UI: `http://127.0.0.1:8000/api/docs/`
- OpenAPI JSON: `http://127.0.0.1:8000/api/schema/`
- Alignment Swagger: `http://127.0.0.1:8000/api/alignment/docs/`
- Alignment schema: `http://127.0.0.1:8000/api/alignment/schema/`

Регламент синка и сигнал готовности endpoint:

- `docs/backend/FRONTEND_BACKEND_SYNC_PROTOCOL.md`

Краткий handoff для backend по текущему спринту:

- `docs/backend/BACKEND_REQUESTS_NOW.md`

## 2) Frontend env (baseline для честного live smoke)

```env
VITE_API_SOURCE=live
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_API_PREFIX=/api
VITE_API_MOCK_FALLBACK=false
VITE_API_MOCK_LATENCY_MS=120
```

- `VITE_API_MOCK_FALLBACK=false` обязателен для integration smoke.
- `true` допустимо только для временной локальной отладки.

## 3) Тестовые креды

- `employee_test / AtomTest123!`
- `manager_test / AtomTest123!`
- `company_admin_test / AtomTest123!`
- `super_admin_test / AtomTest123!`

## 4) Employee vertical — P0 endpoints

1. `GET /api/workspace`
2. `GET /api/employees/me`
3. `GET /api/employees/{employee_id}`
4. `PATCH /api/employees/me`
5. `POST /api/workspace/quick-tasks`

## 5) Auth / CSRF для write

Session-auth + CSRF. Для `PATCH` / `POST` / `PUT` / `DELETE`:

- cookie `csrftoken`
- заголовок `X-CSRFToken: <csrftoken>`
- заголовок `Referer`, согласованный с origin бэка (при локали на `127.0.0.1:8000` обычно `http://127.0.0.1:8000/`)

Если фронт открыт с другого origin, **Referer должен совпадать с тем, что ожидает CSRF/trusted origin на backend** — при расхождении ловится `403`.

## 6) Минимальный live smoke

1. `POST /api/auth/login` → `200`
2. `GET /api/workspace` → `200`
3. `GET /api/employees/me` → `200`
4. `GET /api/employees/emp-2` (или другой коллега из seed) → `200`, `view=public`
5. `PATCH /api/employees/me` → `200`
6. `POST /api/workspace/quick-tasks` → `201`

## 7) Пример `PATCH /api/employees/me`

```json
{
  "city": "Moscow",
  "preferences": {
    "ai_suggestions": true
  }
}
```

## 8) Пример `POST /api/workspace/quick-tasks`

```json
{
  "title": "Frontend live smoke quick task",
  "slot": "today",
  "priority": "high",
  "project_id": "pr-1"
}
```

## 9) Ошибки

- `401` — session после логина
- `403` — CSRF (`csrftoken`, `X-CSRFToken`, `Referer` / trusted origins)
- `404` — сверить путь с `docs/backend/BACKEND_HANDOFF.md`
- `400` — DRF `detail` или field errors в JSON
