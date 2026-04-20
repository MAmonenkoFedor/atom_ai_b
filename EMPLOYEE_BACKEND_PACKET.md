# Employee Backend Packet (send-to-team)

Дата: 2026-04-17  
Статус: готово к отправке backend-команде

## 1) Цель спринта

Закрыть live-контур сотрудника для frontend-маршрутов:
- `/app/workspace`
- `/app/employee/me`
- `/app/employee/:employeeId`

Фронт уже готов принимать live-ответы и отправляет patch/create запросы в snake_case.

## 2) Приоритетные endpoint-ы (в порядке реализации)

1. `GET /api/workspace`
2. `GET /api/employees/me`
3. `GET /api/employees/{employee_id}` (owner/public split)
4. `PATCH /api/employees/me`
5. `POST /api/workspace/quick-tasks`

## 3) Контракт по каждому endpoint

### 3.1 GET /api/workspace

Назначение: обогащенный workspace текущего пользователя.

Must-have поля в ответе:
- `employee`
- `greeting`
- `today_focus` (или `todayFocus`)
- `stats`
- `tasks_grouped` (или `tasksGrouped`) с группами `overdue | today | this_week | later | done`
- `project_context` (или `projectContext`)
- `activity_feed` (или `activityFeed`)
- `ai_context` (или `aiContext`)
- `quick_actions` (или `quickActions`)
- `role_extras` (или `roleExtras`, optional)
- `viewer_role` (или `viewerRole`)

Пример:
```json
{
  "employee": {
    "id": "e1",
    "full_name": "Alex Kim",
    "role": "Frontend Engineer",
    "email": "alex@company.com",
    "status": "online"
  },
  "greeting": {
    "user_name": "Alex",
    "time_greeting": "Доброе утро",
    "focus_message": "Сегодня закрываем интеграцию профиля"
  },
  "tasks_grouped": [
    { "key": "today", "label": "Сегодня", "tasks": [] }
  ],
  "viewer_role": "employee"
}
```

---

### 3.2 GET /api/employees/me

Назначение: owner-mode профиль текущего пользователя.

Must-have:
- `view: "owner"`
- `header`
- `contacts` (private)
- `performance`
- `projects`
- `achievements`
- `bonus_goals` (или `bonusGoals`)
- `activity_feed` (или `activityFeed`)
- `comments_history` (или `commentsHistory`)
- `preferences`
- `editable_fields` (или `editableFields`)

---

### 3.3 GET /api/employees/{employee_id}

Назначение: единый endpoint owner/public профиля.

Правило:
- если `employee_id == current_user.id` -> вернуть owner-модель (`view: "owner"`)
- иначе -> вернуть public-модель (`view: "public"`)

Public-модель:
- `header`
- `contacts` (только публичные поля: `telegram`, `work_email` если разрешено)
- `public_projects` (или `publicProjects`)
- `public_achievements` (или `publicAchievements`)
- `public_stats` (или `publicStats`)

Критично: не отдавать private-поля в public-режиме.

---

### 3.4 PATCH /api/employees/me

Назначение: обновление редактируемых owner-полей.

Request (snake_case):
```json
{
  "personal_email": "alex.personal@gmail.com",
  "phone": "+79999999999",
  "telegram": "@alex",
  "city": "Moscow",
  "working_hours": "10:00 - 19:00",
  "timezone": "Europe/Moscow",
  "preferences": {
    "email_digest": "daily",
    "task_reminders": true,
    "mentions_push": true,
    "ai_suggestions": false
  }
}
```

Ответ: полный актуальный owner-профиль (как в `GET /api/employees/me`).

---

### 3.5 POST /api/workspace/quick-tasks

Назначение: быстрое создание задачи из workspace.

Request:
```json
{
  "title": "Подготовить weekly summary",
  "slot": "today",
  "priority": "high",
  "project_id": "p1"
}
```

Response:
```json
{
  "task_id": "t-1001",
  "slot": "today",
  "title": "Подготовить weekly summary"
}
```

## 4) Error policy

Поддержать DRF-совместимый формат:
- `400` validation -> `{ "detail": "..." }` или field-errors
- `401` unauthorized/session expired
- `403` forbidden
- `404` not found

## 5) Seed data (обязательно для frontend smoke)

Минимально:
- роли: `employee`, `manager`, `company_admin`
- не меньше 3 сотрудников в одной компании
- задачи в группах: `overdue`, `today`, `this_week`, `later`, `done`
- минимум 1 activity item с `actor`, чтобы проверить переход на профиль коллеги

Пример activity item с actor:
```json
{
  "id": "a1",
  "type": "task",
  "title": "Обновлена задача",
  "timestamp": "2026-04-17T10:00:00Z",
  "href": "/app/tasks/t1",
  "actor": {
    "id": "e2",
    "name": "Maria Smirnova"
  }
}
```

## 6) Definition of done (backend)

Считаем этап завершенным, когда:
1. все 5 endpoint-ов выше работают по контракту;
2. OpenAPI обновлен;
3. frontend проходит live smoke с `VITE_API_SOURCE=live` и `VITE_API_MOCK_FALLBACK=false`:
   - login -> `/app/workspace`
   - `/app/employee/me`
   - `/app/employee/:colleagueId` (public)
   - patch контактов/preferences
   - quick-task create и появление в workspace.

## 7) Что отправить в ответ frontend-команде

- base URL стенда
- тестовые креды по ролям (`employee`, `manager`, `company_admin`)
- список готовых endpoint-ов
- список известных ограничений
- ссылка на актуальный OpenAPI
