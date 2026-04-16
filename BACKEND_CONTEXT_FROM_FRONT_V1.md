# Backend Context From `front_v1.docx`

Дата: 2026-04-15
Источник: `d:\ATOM_AI_backend\front_v1.docx` (Unified Frontend Execution Plan)

## 1) Что фронтенд зафиксировал как основу

- Единая ролевая модель: `employee`, `manager`, `company_admin`, `super_admin`.
- Доступ должен проверяться на двух уровнях:
  - route-level;
  - feature/action-level (policy guard).
- Для новых фич обязательны contract-first и domain-first принципы:
  - UI не должен зависеть от raw API shape;
  - live и mock должны иметь совместимую форму контракта.

## 2) Что это означает для backend

- Нужны стабильные и предсказуемые API-контракты по приоритетным доменам:
  - auth/session;
  - workspace/profile;
  - org drill-down;
  - tasks;
  - projects;
  - company-admin endpoints.
- Для endpoint-ов с role-sensitive операциями нужна явная серверная авторизация:
  - недостаточно, что фронт скрывает кнопки;
  - критичные действия должны валидироваться на backend policy уровне.
- Любое расхождение с согласованным контрактом фиксируется как `gap`, а не переносится в UI-логику.

## 3) Приоритет интеграции (frontend smoke order)

Фронтенд ожидает, что в первую очередь стабильно работают:

1. `auth/login/me`
2. `workspace`
3. `employee profile`
4. `org drill-down`
5. `tasks`
6. `projects`
7. `company admin endpoints`

## 4) Контрактные требования к ответам

- Единообразная структура успешных ответов и пагинации.
- Детерминированный query/filter behavior.
- Понятные `4xx` ошибки для invalid query/action.
- Минимизация drift между OpenAPI/DRF контрактом и фактическим live-ответом.

Отдельно учесть текущий риск:

- В проекте включен unified error handler (`error` wrapper),
- а часть frontend-ожиданий описана в DRF-стиле `detail`.
- Это нужно согласовать по каждому критичному домену, чтобы не ломать адаптеры.

## 5) Ролевой минимум для backend policy

- `employee`: только own/workspace scope.
- `manager`: team/department scope без company-wide admin действий.
- `company_admin`: company scope (employees/invitations/roles/projects/settings).
- `super_admin`: cross-company/platform scope.

Рекомендуется:

- централизовать проверку scope и role policies в переиспользуемом слое;
- не дублировать правила в каждом view отдельно.

## 6) Прямо сейчас (короткий backend plan)

1. Зафиксировать role-policy матрицу на backend (permission + object scope).
2. Провести smoke по приоритетному списку frontend (см. раздел 3).
3. Сформировать и вести `gap list` по расхождениям live API vs contract.
4. Согласовать единый error contract для frontend-критичных endpoint-ов.
5. Добавить точечные integration tests для критичных user journeys.

## 7) Что уже покрыто в текущем репозитории

- Есть `workspace/profile` read-only контур + alias endpoint-ы.
- Есть `projects`, `chats`, `ai runs`, `ai run logs` с фильтрами.
- Есть foundation (OpenAPI, health, pagination, базовая структура доменов).

Остается усилить:

- role-policy enforcement для admin/company/platform сценариев;
- единый и согласованный error contract;
- интеграционные проверки в порядке frontend-приоритета.
