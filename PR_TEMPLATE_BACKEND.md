# PR Template (Backend)

Использовать как текст PR-описания.

## 1) Scope

- Модули:
- Endpoint'ы:
- Что изменено:

## 2) Contract Delta

- Изменения API:
- Обновленные документы:
  - `API_BACKEND_PARALLEL_REQUESTS_v2.md`:
  - `OPENAPI_SCHEMA_LOCK_v2.md`:

## 3) Validation

- `manage.py check`:
- `spectacular --validate`:
- `audit_gate.ps1 -Mode Fast`:
- `audit_gate.ps1 -Mode Full`:
- Smoke report artifact (`smoke_report.json`):

## 4) Permissions / Security

- Что проверено по auth/roles/permissions:
- Какие write endpoint'ы покрыты негативными кейсами:

## 5) Data / Migrations

- Изменения моделей:
- Миграции:
- Результат применения миграций локально:

## 6) Risks / Follow-ups

- Ограничения:
- Риски:
- Follow-up задачи:

## 7) Rollback Plan

- Как откатить изменения при проблеме:
