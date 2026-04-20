# Frontend–Backend sync protocol

Дата: 2026-04-20  
Статус: официальный регламент синка без лишних созвонов

## 1) Цель

- backend передаёт изменения в одном стабильном формате;
- frontend быстро отвечает `pass/fail` и списком mismatch;
- drift контракта ловится до UI-регрессий.

## 2) Текущий статус Employee vertical (live)

- `POST /api/auth/login` → `200`
- `GET /api/workspace` → `200`
- `GET /api/employees/me` → `200`
- `GET /api/employees/emp-2` → `200` (`view=public`)
- `PATCH /api/employees/me` → `200`
- `POST /api/workspace/quick-tasks` → `201`

Актуальные приоритеты и открытые вопросы: `docs/backend/BACKEND_REQUESTS_NOW.md`.

## 3) Что уже подключено на frontend

- Live auth: `/api/auth/login` + `/api/auth/session`
- Cookie-based auth mode
- CSRF для write: `X-CSRFToken` + `Referer`
- Snake_case для `PATCH /api/employees/me` и `POST /api/workspace/quick-tasks`
- Нормализаторы: owner/public profile, editable fields, `header.status` / `header.title`

## 4) Формат changelog по endpoint

Для каждого изменённого endpoint — короткий блок:

1. `endpoint`
2. что поменялось (поля / типы / enum)
3. `backward_compatible` (`yes` / `no`)
4. `change_date` (`YYYY-MM-DD`)

Пример:

```yaml
endpoint: "PATCH /api/employees/me"
changes:
  - "preferences.ai_suggestions: bool (unchanged)"
  - "contacts.city: string (updated validation)"
backward_compatible: "yes"
change_date: "2026-04-20"
```

## 5) Payload policy

- request/response по умолчанию в **snake_case**;
- frontend нормализует в **camelCase**;
- исключения — явно в changelog и OpenAPI.

## 6) Employee profile: стабильность `header`

- заранее фиксируем source-of-truth: **`role` или `title`**;
- не менять оба поля одновременно без предупреждения в changelog;
- если оба поля остаются — в changelog указать каноническое поле для UI.

## 7) Error contract

- `400` — field errors или `detail`;
- `401` / `403` / `404` — понятный `detail`;
- API не отдаёт HTML/plain text вместо JSON.

## 8) Demo data (минимум для frontend smoke)

- роли: `employee`, `manager`, `company_admin`;
- минимум один коллега для public profile;
- задачи по группам: `overdue`, `today`, `this_week`, `later`, `done`;
- минимум один activity item с `actor`.

## 9) Сигнал готовности endpoint (шаблон)

```yaml
ready_for_front: true
tested_by_backend: true
openapi_section: "http://127.0.0.1:8000/api/docs/"
endpoint: "POST /api/workspace/quick-tasks"
backward_compatible: true
change_date: "2026-04-20"
request_example:
  title: "Frontend live smoke quick task"
  slot: "today"
  priority: "high"
  project_id: "pr-1"
response_success_example:
  task_id: "t-2001"
  slot: "today"
  title: "Frontend live smoke quick task"
response_error_example:
  detail: "Invalid slot. Allowed: today, this_week, later."
```

## 10) Процесс обновлений

1. Backend обновляет OpenAPI + короткий changelog (см. §4).
2. Backend пишет в чат: **готово к frontend smoke**.
3. Frontend отвечает: **`pass` / `fail` + mismatch list**.
4. При mismatch backend правит и повторно шлёт сигнал из §9.
5. Финальная фиксация — в `docs/backend/BACKEND_HANDOFF.md` и schema.

## 11) Next sync (совместно)

- кодировка / локализация текстов в `workspace`;
- канон `header.role` vs `header.title`;
- совместный UI smoke (см. `docs/backend/LIVE_CONNECTION_GUIDE.md`);
- после sync — OpenAPI + `BACKEND_HANDOFF`.
