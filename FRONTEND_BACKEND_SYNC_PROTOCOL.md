# Frontend/Backend Sync Protocol

Дата: 2026-04-17  
Статус: обязательный формат синхронизации изменений API

## 1) Цель

Ускорить интеграцию без лишних созвонов:

- backend передает изменения в одном стабильном формате;
- frontend быстро валидирует и возвращает mismatch list;
- contract drift фиксируется до UI-регрессий.

## 2) Формат changelog по endpoint

Для каждого измененного endpoint отправляется короткий блок:

1. `endpoint`
2. `что поменялось` (поля/типы/enum)
3. `backward_compatible` (`yes/no`)
4. `change_date` (`YYYY-MM-DD`)

Пример:

```yaml
endpoint: "PATCH /api/employees/me"
changes:
  - "preferences.ai_suggestions: bool (no change)"
  - "contacts.city: string (updated validation)"
backward_compatible: "yes"
change_date: "2026-04-17"
```

## 3) Payload policy

- request/response по умолчанию в `snake_case`;
- frontend нормализует в `camelCase` на своей стороне;
- любые исключения фиксируются явно в changelog и OpenAPI.

## 4) Employee profile stability policy

Для блока `header`:

- заранее фиксируем source-of-truth: `role` или `title`;
- не меняем одновременно оба поля без предупреждения;
- если оба поля присутствуют, в changelog явно указываем canonical field.

## 5) Error contract policy

- `400` -> field errors или `detail`;
- `401/403/404` -> понятный `detail`;
- API endpoints не возвращают HTML/text вместо JSON.

## 6) Demo data policy (frontend smoke)

Обязательный минимальный набор:

- роли: `employee`, `manager`, `company_admin`;
- минимум 1 коллега для public profile;
- задачи по группам: `overdue`, `today`, `this_week`, `later`, `done`;
- минимум 1 activity item с `actor`.

## 7) Endpoint readiness signal

Каждый endpoint после backend-проверки передается в таком формате:

```yaml
ready_for_front: true
tested_by_backend: true
openapi_section: "http://127.0.0.1:8000/api/docs/"
endpoint: "POST /api/workspace/quick-tasks"
backward_compatible: true
change_date: "2026-04-17"
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

## 8) Update flow

1. Backend обновляет OpenAPI + короткий changelog.
2. Backend пишет в чат: `готово к frontend smoke`.
3. Frontend отвечает: `pass/fail + mismatch list`.
4. При mismatch backend фиксит и повторно отправляет readiness signal.
