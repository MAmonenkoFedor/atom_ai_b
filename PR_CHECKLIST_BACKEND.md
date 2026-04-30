# PR Checklist (Backend, Audit-Ready)

Использовать в каждом PR перед запросом ревью.

## 1) Scope и контракт

- [ ] Scope изменения описан (какие модули/endpoint'ы затронуты).
- [ ] При изменении API обновлены контрактные документы:
  - `API_BACKEND_PARALLEL_REQUESTS_v2.md` (если менялся контракт для frontend)
  - `OPENAPI_SCHEMA_LOCK_v2.md` (если менялись endpoint'ы/схемы)
- [ ] Для новых endpoint'ов зафиксированы `operationId` и request/response схемы.

## 2) Код и миграции

- [ ] Код проходит локальную проверку:
  - `.\.venv\Scripts\python.exe manage.py check`
- [ ] Если изменялись модели:
  - создана и применена миграция локально
  - нет "висящих" model changes без migration
- [ ] Для write endpoint'ов проверены auth/permission policy.

## 3) Schema и smoke

- [ ] Access privacy defaults green:
  - `.\.venv\Scripts\python.exe manage.py seed_access_control`
  - `.\.venv\Scripts\python.exe manage.py check_access_privacy_defaults`
- [ ] OpenAPI validate зеленый:
  - `.\.venv\Scripts\python.exe manage.py spectacular --validate --file alignment_openapi.yaml --urlconf config.alignment_schema_urls`
- [ ] Прогнан audit gate:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\audit_gate.ps1 -BaseUrl http://127.0.0.1:8000/api -Mode Fast`
- [ ] Перед handoff/релизом прогнан `Full`:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\audit_gate.ps1 -BaseUrl http://127.0.0.1:8000/api -Mode Full`
- [ ] Сформирован smoke JSON отчет (`smoke_report.json`) и приложен/сохранен как артефакт.

## 4) Handoff и риски

- [ ] Обновлен `SPRINT_HANDOFF_CHECKLIST.md` по фактическим результатам.
- [ ] При необходимости обновлен `PROJECT_PROGRESS_REPORT.md`.
- [ ] В PR описаны:
  - что сделано
  - что проверено
  - риски/ограничения и follow-up задачи

## 5) Запрещено к merge

- [ ] Нет merge при красном smoke или schema validate.
- [ ] Нет merge изменения поведения endpoint без обновления contract docs.
- [ ] Нет "временных" прав/ролей без явной фиксации в документации.
