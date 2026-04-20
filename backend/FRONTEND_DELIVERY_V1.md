# Frontend Delivery Packet v1

Дата: 2026-04-20  
Статус: готово к пересылке frontend-команде

## 1) Назначение

Единый v1-документ для frontend: что уже работает в live, какие endpoint-ы использовать, как передавать изменения и как подтверждать готовность без лишних созвонов.

## 2) Базовые ссылки

- Live base URL: `http://127.0.0.1:8000/api`
- Swagger: `http://127.0.0.1:8000/api/docs/`
- OpenAPI: `http://127.0.0.1:8000/api/schema/`
- Alignment Swagger: `http://127.0.0.1:8000/api/alignment/docs/`
- Alignment schema: `http://127.0.0.1:8000/api/alignment/schema/`

Канонические документы:

- `backend/BACKEND_HANDOFF.md`
- `backend/LIVE_CONNECTION_GUIDE.md`
- `backend/FRONTEND_BACKEND_SYNC_PROTOCOL.md`
- `backend/BACKEND_REQUESTS_NOW.md`

## 3) Что уже работает в live

- `POST /api/auth/login` -> `200`
- `GET /api/workspace` -> `200`
- `GET /api/employees/me` -> `200`
- `GET /api/employees/emp-2` -> `200` (`view=public`)
- `PATCH /api/employees/me` -> `200`
- `POST /api/workspace/quick-tasks` -> `201`
- `GET/POST/PATCH/DELETE /api/workspace/tasks*` (alias с обязательными `building_id` и `floor_id`) -> работает в smoke

## 4) Тестовые креды

- `employee_test / Pass12345!`
- `manager_test / Pass12345!`
- `company_admin_test / Pass12345!`
- `super_admin_test / Pass12345!`

## 5) Контракт v1 для frontend

1. Payload policy:
   - request/response по умолчанию `snake_case`
   - frontend нормализует в `camelCase` на своей стороне
2. Employee profile policy:
   - `header.role` = source-of-truth
   - `header.title` = display label
3. Timestamp policy:
   - `ISO-8601 Z` (без `+03:00` в API payload)
4. Error policy:
   - `400`: field-errors или `{ "detail": "..." }`
   - `401/403/404`: `{ "detail": "..." }`
   - API не возвращает HTML/plain text вместо JSON
5. Auth/CSRF for write:
   - cookie `csrftoken`
   - header `X-CSRFToken`
   - header `Referer` (согласован с backend origin/trusted origins)

## 6) Правила общения backend <-> frontend

1. Любое изменение endpoint отправляется блоком changelog:
   - endpoint
   - что поменялось (поля/типы/enum)
   - backward_compatible (`yes/no`)
   - change_date (`YYYY-MM-DD`)
2. Backend сначала обновляет OpenAPI, потом пишет в чат `готово к frontend smoke`.
3. Frontend отвечает только в формате:
   - `pass` или `fail`
   - `mismatch list` (поинтами, без общего текста)
4. Если `fail`, backend фиксит и повторно отправляет readiness signal.

## 7) Readiness signal (шаблон в чат)

```yaml
ready_for_front: true
tested_by_backend: true
endpoint: "PATCH /api/employees/me"
openapi_section: "http://127.0.0.1:8000/api/docs/"
backward_compatible: true
change_date: "2026-04-20"
request_example:
  city: "Moscow"
response_success_example:
  view: "owner"
response_error_example:
  detail: "Invalid payload."
```

## 8) Frontend smoke v1 (обязательный)

1. `POST /api/auth/login`
2. `GET /api/workspace`
3. `GET /api/employees/me`
4. `GET /api/employees/{colleague_id}` -> `view=public`
5. `PATCH /api/employees/me`
6. `POST /api/workspace/quick-tasks`
7. `GET /api/workspace/tasks?building_id=...&floor_id=...`

## 9) Известные ограничения v1

- `workspace/tasks` пока реализован как alias-слой для employee vertical и будет расширяться до полного floor-scoped canonical набора.
- Для честного integration smoke фронт должен работать с `VITE_API_MOCK_FALLBACK=false`.

## 10) План продолжения после v1

1. Расширить `workspace/tasks` до полного набора contract-операций (audit/comments/checklist).
2. Довести canonical floor-scoped tasks routes до полного соответствия handoff.
3. После каждого шага отправлять readiness signal и проходить совместный UI smoke.
