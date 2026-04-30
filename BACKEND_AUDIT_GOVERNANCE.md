# Backend Audit Governance (Audit-Ready Rules)

Дата фиксации: 2026-04-16
Область: весь backend (`/api`, `/api/v1`, schema, smoke, handoff)

## 1. Цель

Документ задает обязательные правила расширения backend, чтобы проект проходил полный технический аудит без "ручных договоренностей" и разночтений по контрактам.

## 2. Базовые принципы

1. Contract-first:
   - сначала обновляется контракт (`API_BACKEND_PARALLEL_REQUESTS_v2.md`, `OPENAPI_SCHEMA_LOCK_v2.md`);
   - затем код и smoke.
2. Single source of truth:
   - прод endpoint-контракты фиксируются в schema + lock-доках, а не в чатах.
3. Traceability:
   - каждое изменение должно быть прослеживаемо: "требование -> код -> smoke -> отчет".
4. Backward compatibility:
   - alias/legacy endpoints не удаляются без согласованного deprecation-плана.
5. Deterministic checks:
   - перед handoff/merge всегда запускается единый gate-процесс.

## 3. Правила расширения API (обязательно)

1. Любой новый endpoint:
   - должен иметь явные request/response схемы;
   - должен иметь `operationId`;
   - должен быть отражен в OpenAPI.
2. Любой write endpoint (`POST/PATCH/PUT/DELETE`):
   - проверяется в smoke (успешный и минимум один негативный сценарий);
   - должен соблюдать auth/permission policy.
3. Ошибки:
   - для frontend-критичных путей используем DRF-формат `{ "detail": "..." }`.
4. Пагинация:
   - если endpoint list-heavy, явно фиксируется формат (`results/count` или cursor-policy).
5. CSV/файловые ответы:
   - обязательна проверка заголовков (`Content-Type`, `Content-Disposition`).

## 4. Правила изменений данных и миграций

1. Любое изменение модели:
   - сопровождается миграцией;
   - проходит `manage.py migrate` локально.
2. Seed/test users:
   - после изменений auth/role обязательно проверяется `seed_test_credentials`.
3. Нельзя "прятать" breaking changes:
   - если есть несовместимость, обновляется контракт и handoff-документация в тот же change-set.

## 5. Обязательный Gate Перед Merge/Handoff

Запускать:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\audit_gate.ps1 -BaseUrl http://127.0.0.1:8000/api -Mode Full
```

Gate включает:

1. `python manage.py check`
2. `python manage.py seed_access_control`
3. `python manage.py check_access_privacy_defaults`
4. `python manage.py spectacular --validate --file alignment_openapi.yaml --urlconf config.alignment_schema_urls`
5. `SMOKE_RUNNER.ps1` (`Fast` или `Full`)
6. JSON-отчет smoke для артефактов handoff

Privacy note:
- `check_access_privacy_defaults` обязателен для контроля policy-инварианта:
  - `company_admin_base` по умолчанию содержит только `ai.workspace.view_metadata`;
  - `ai.workspace.view_content` не должен включаться в шаблон по умолчанию.

## 6. Definition of Done (DoD) для backend-задачи

Задача считается завершенной только если:

1. Код реализован и проходит локальные проверки.
2. Контрактные документы обновлены при изменении API.
3. OpenAPI валиден без ошибок.
4. Smoke-проверки зеленые.
5. Есть запись в handoff/progress (что сделано, что проверено, риски).

## 7. Контроль процесса (операционно)

1. Перед началом задачи:
   - явно фиксируем scope endpoint'ов и expected statuses.
2. В процессе:
   - работаем небольшими инкрементами;
   - после каждого инкремента прогоняем минимум `Fast` smoke.
3. Перед сдачей:
   - прогоняем `Full` smoke + schema validate + формируем JSON отчет.
4. После сдачи:
   - обновляем `SPRINT_HANDOFF_CHECKLIST.md` и при необходимости `PROJECT_PROGRESS_REPORT.md`.

## 8. Антипаттерны (запрещено)

1. Менять поведение endpoint без обновления contract docs.
2. Мержить изменения при красном smoke/schema validate.
3. Оставлять "временные" роли/permissions без явной фиксации.
4. Полагаться на ручную проверку без воспроизводимого скрипта.

## 9. Минимальный шаблон отчета по задаче

1. Scope: какие endpoint'ы/модули изменены.
2. Contract delta: что изменилось в API.
3. Validation:
   - check
   - schema validate
   - smoke (Fast/Full)
4. Risks/Follow-ups.

