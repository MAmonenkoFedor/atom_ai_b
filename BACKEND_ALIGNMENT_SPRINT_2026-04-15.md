# Backend Alignment Sprint — Execution (Projects / Company Admin / Super Admin / Audit / Action Center)

Дата: 2026-04-15
Статус: in progress (frontend side prepared)
Источник контракта: `docs/API_BACKEND_PARALLEL_REQUESTS_v2.md`

## 1) Цель спринта

Синхронизировать frontend и backend по:
- финальным URL,
- OpenAPI схемам,
- live-готовности вертикалей:
  - projects
  - company admin
  - super admin
  - platform audit
  - admin action center

## 2) Definition of Done (Sprint)

1. Все endpoint'ы из `OPENAPI_SCHEMA_LOCK_v2.md` присутствуют в `/schema/`.
2. Swagger/ReDoc показывает корректные request/response для write/read операций.
3. Smoke checklist пройден в live-режиме без mock fallback.
4. Backend и frontend согласовали alias policy (primary + fallback URL).
5. Все критичные расхождения зафиксированы как отдельные issue с owner и ETA.

## 3) Sprint tasks

## 3.1 Backend

1. Реализовать endpoint'ы по `docs/OPENAPI_SCHEMA_LOCK_v2.md`.
2. Проставить operationId и схемы ответа (DRF serializers).
3. Опубликовать `/schema/`, Swagger, ReDoc.
4. Выдать test credentials:
   - `company_admin`
   - `super_admin`

## 3.2 Frontend

1. Запустить live mode:
   - `VITE_API_SOURCE=live`
   - `VITE_API_MOCK_FALLBACK=false`
2. Пройти smoke flow:
   - projects list/details/create
   - company admin users/invites/role update
   - super admin tenants/invites/status
   - platform audit filters/export
   - action center list/details
3. Зафиксировать несовпадения payload/enum/status code.

## 4) Smoke run commands

1. Подготовить `.env.local`:

```env
VITE_API_SOURCE=live
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_API_PREFIX=/api
VITE_API_MOCK_FALLBACK=false
VITE_API_MOCK_LATENCY_MS=0
```

2. Запуск:

```bash
npm install
npm run dev
```

3. Проверка качества сборки:

```bash
npm run check
```

## 5) Risk register

1. Разные enum значения между frontend и backend.
2. Несовместимый формат list-ответов (`array` vs `{results,count}`).
3. CSV export может вернуться JSON вместо raw text/csv.
4. Детали action center могут не содержать `related_links`.
5. Alias endpoint'ы не подняты (frontend fallback включается, но это сигнал долга).

## 6) Escalation rules

1. Blocker по auth/session: критично, фикс в текущий день.
2. Blocker по write endpoints (POST/PATCH/DELETE): критично, фикс в текущий день.
3. Mismatch только в поле, которое normalizer уже поддерживает: не блокер, в backlog.

## 7) Daily sync template

- Что реализовано backend (endpoint + schema)
- Что проверено frontend (screen + role)
- Что не совпало (пример payload)
- Кто владелец фикса
- ETA
