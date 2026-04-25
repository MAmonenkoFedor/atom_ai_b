"""Seed data for the access-control service.

The seed is *idempotent* — running it repeatedly converges the DB to the
shipped catalog without destroying manual edits (manual-only fields like
``is_active`` are preserved if the operator has changed them).

Use via the management command ``manage.py seed_access_control``.
"""

from __future__ import annotations

from typing import Iterable

from django.db import transaction

from apps.access.models import (
    DelegationRule,
    PermissionDefinition,
    RoleTemplate,
    RoleTemplatePermission,
    SCOPE_COMPANY,
    SCOPE_DEPARTMENT,
    SCOPE_GLOBAL,
    SCOPE_PROJECT,
    SCOPE_SELF,
)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


# fmt: off
CORE_PERMISSIONS: list[dict] = [
    # --- Organization -------------------------------------------------------
    {
        "code": "department.create",
        "name": "Создание отделов",
        "module": PermissionDefinition.MODULE_ORGANIZATION,
        "allowed_scopes": [SCOPE_COMPANY],
        "can_be_delegated": False,
        "is_sensitive": True,
        "description": "Создание новых отделов в оргструктуре компании.",
    },
    {
        "code": "department.edit",
        "name": "Редактирование отделов",
        "module": PermissionDefinition.MODULE_ORGANIZATION,
        "allowed_scopes": [SCOPE_COMPANY, SCOPE_DEPARTMENT],
        "can_be_delegated": True,
        "is_sensitive": False,
        "description": "Изменение названия, описания и параметров отдела.",
    },
    {
        "code": "department.assign_members",
        "name": "Назначение сотрудников в отдел",
        "module": PermissionDefinition.MODULE_ORGANIZATION,
        "allowed_scopes": [SCOPE_COMPANY, SCOPE_DEPARTMENT],
        "can_be_delegated": True,
        "is_sensitive": False,
        "description": "Добавление, удаление, смена позиции сотрудника в отделе.",
    },
    # --- Projects -----------------------------------------------------------
    {
        "code": "project.create",
        "name": "Создание проектов",
        "module": PermissionDefinition.MODULE_PROJECTS,
        "allowed_scopes": [SCOPE_COMPANY],
        "can_be_delegated": False,
        "is_sensitive": True,
        "description": "Создание нового проекта внутри компании.",
    },
    {
        "code": "project.edit",
        "name": "Редактирование проекта",
        "module": PermissionDefinition.MODULE_PROJECTS,
        "allowed_scopes": [SCOPE_COMPANY, SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
        "description": "Изменение параметров и настроек проекта.",
    },
    {
        "code": "project.assign_members",
        "name": "Назначение участников проекта",
        "module": PermissionDefinition.MODULE_PROJECTS,
        "allowed_scopes": [SCOPE_COMPANY, SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
        "description": "Добавление и удаление участников, смена их проектной роли.",
    },
    {
        "code": "project.assign_rights",
        "name": "Выдача прав внутри проекта",
        "module": PermissionDefinition.MODULE_PROJECTS,
        "allowed_scopes": [SCOPE_COMPANY, SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": True,
        "description": "Выдача / отзыв проектных прав другим участникам.",
    },
    {
        "code": "project.chat.moderate",
        "name": "Модерация проектного чата",
        "module": PermissionDefinition.MODULE_PROJECTS,
        "allowed_scopes": [SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
        "description": "Управление участниками и настройками чата проекта.",
    },
    # --- Documents ---------------------------------------------------------
    {
        "code": "docs.view",
        "name": "Просмотр документов",
        "module": PermissionDefinition.MODULE_DOCUMENTS,
        "allowed_scopes": [SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
        "description": "Чтение документов в рамках выбранного контекста.",
    },
    {
        "code": "docs.upload",
        "name": "Загрузка документов",
        "module": PermissionDefinition.MODULE_DOCUMENTS,
        "allowed_scopes": [SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
        "description": "Загрузка новых документов.",
    },
    {
        "code": "docs.edit",
        "name": "Редактирование документов",
        "module": PermissionDefinition.MODULE_DOCUMENTS,
        "allowed_scopes": [SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
        "description": "Изменение содержимого и атрибутов документа.",
    },
    {
        "code": "docs.delete",
        "name": "Удаление документов",
        "module": PermissionDefinition.MODULE_DOCUMENTS,
        "allowed_scopes": [SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": True,
        "description": "Удаление документа (мягкое / жёсткое).",
    },
    {
        "code": "docs.assign_editors",
        "name": "Назначение редакторов документа",
        "module": PermissionDefinition.MODULE_DOCUMENTS,
        "allowed_scopes": [SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
        "description": "Выбор, кто может редактировать документ.",
    },
    # Project-scoped aliases (операционный пакет «документы проекта» у руководителя)
    {
        "code": "project.docs.view",
        "name": "Просмотр документов проекта",
        "module": PermissionDefinition.MODULE_DOCUMENTS,
        "allowed_scopes": [SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
        "description": "Чтение всех документов в рамках проекта.",
    },
    {
        "code": "project.docs.upload",
        "name": "Загрузка документов проекта",
        "module": PermissionDefinition.MODULE_DOCUMENTS,
        "allowed_scopes": [SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
        "description": "Добавление файлов и ссылок в документы проекта.",
    },
    {
        "code": "project.docs.edit",
        "name": "Редактирование документов проекта",
        "module": PermissionDefinition.MODULE_DOCUMENTS,
        "allowed_scopes": [SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
        "description": "Изменение метаданных и содержимого документов проекта.",
    },
    {
        "code": "project.docs.assign_editors",
        "name": "Назначение ответственных за документацию проекта",
        "module": PermissionDefinition.MODULE_DOCUMENTS,
        "allowed_scopes": [SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
        "description": "Назначение редакторов и владельцев контента по документам проекта.",
    },
    # --- Tasks -------------------------------------------------------------
    {
        "code": "tasks.view",
        "name": "Просмотр задач",
        "module": PermissionDefinition.MODULE_TASKS,
        "allowed_scopes": [SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
        "description": "Просмотр списка и карточек задач в выбранном контексте.",
    },
    {
        "code": "tasks.create",
        "name": "Создание задач",
        "module": PermissionDefinition.MODULE_TASKS,
        "allowed_scopes": [SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
    },
    {
        "code": "tasks.assign",
        "name": "Назначение задач",
        "module": PermissionDefinition.MODULE_TASKS,
        "allowed_scopes": [SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
    },
    {
        "code": "tasks.edit",
        "name": "Редактирование задач",
        "module": PermissionDefinition.MODULE_TASKS,
        "allowed_scopes": [SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
    },
    {
        "code": "tasks.change_deadline",
        "name": "Изменение дедлайнов",
        "module": PermissionDefinition.MODULE_TASKS,
        "allowed_scopes": [SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
    },
    {
        "code": "tasks.block",
        "name": "Блокировка задач",
        "module": PermissionDefinition.MODULE_TASKS,
        "allowed_scopes": [SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": True,
    },
    # Project-scoped task aliases (операционный пакет «задачи проекта»)
    {
        "code": "project.tasks.view",
        "name": "Просмотр задач проекта",
        "module": PermissionDefinition.MODULE_TASKS,
        "allowed_scopes": [SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
        "description": "Видеть задачи, привязанные к проекту.",
    },
    {
        "code": "project.tasks.create",
        "name": "Создание задач в проекте",
        "module": PermissionDefinition.MODULE_TASKS,
        "allowed_scopes": [SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
        "description": "Создавать задачи в рамках проекта.",
    },
    {
        "code": "project.tasks.assign",
        "name": "Назначение задач в проекте",
        "module": PermissionDefinition.MODULE_TASKS,
        "allowed_scopes": [SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
        "description": "Назначать исполнителей по задачам проекта.",
    },
    {
        "code": "project.tasks.edit",
        "name": "Редактирование задач проекта",
        "module": PermissionDefinition.MODULE_TASKS,
        "allowed_scopes": [SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
        "description": "Редактировать поля задач в проекте.",
    },
    {
        "code": "project.tasks.change_deadline",
        "name": "Изменение дедлайнов в проекте",
        "module": PermissionDefinition.MODULE_TASKS,
        "allowed_scopes": [SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": False,
        "description": "Менять сроки задач проекта.",
    },
    {
        "code": "project.tasks.block",
        "name": "Блокировка задач в проекте",
        "module": PermissionDefinition.MODULE_TASKS,
        "allowed_scopes": [SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": True,
        "description": "Блокировать задачи в проекте.",
    },
    # --- AI ----------------------------------------------------------------
    {
        "code": "ai.chat.use",
        "name": "Использование AI-чата",
        "module": PermissionDefinition.MODULE_AI,
        "allowed_scopes": [SCOPE_COMPANY, SCOPE_PROJECT, SCOPE_SELF],
        "can_be_delegated": True,
        "is_sensitive": False,
    },
    {
        "code": "ai.models.select",
        "name": "Выбор AI-модели",
        "module": PermissionDefinition.MODULE_AI,
        "allowed_scopes": [SCOPE_COMPANY, SCOPE_PROJECT, SCOPE_SELF],
        "can_be_delegated": True,
        "is_sensitive": False,
    },
    {
        "code": "ai.models.manage",
        "name": "Управление AI-моделями",
        "module": PermissionDefinition.MODULE_AI,
        "allowed_scopes": [SCOPE_GLOBAL, SCOPE_COMPANY],
        "can_be_delegated": False,
        "is_sensitive": True,
        "description": "Подключение, отключение и настройка LLM-провайдеров.",
    },
    # --- Access ------------------------------------------------------------
    {
        "code": "rights.grant",
        "name": "Выдача прав",
        "module": PermissionDefinition.MODULE_ACCESS,
        "allowed_scopes": [SCOPE_GLOBAL, SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": True,
        "description": "Выдача других прав сотрудникам в пределах scope.",
    },
    {
        "code": "rights.revoke",
        "name": "Отзыв прав",
        "module": PermissionDefinition.MODULE_ACCESS,
        "allowed_scopes": [SCOPE_GLOBAL, SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_PROJECT],
        "can_be_delegated": True,
        "is_sensitive": True,
        "description": "Отзыв ранее выданных прав.",
    },
    {
        "code": "roles.assign",
        "name": "Назначение ролей / шаблонов",
        "module": PermissionDefinition.MODULE_ACCESS,
        "allowed_scopes": [SCOPE_GLOBAL, SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_PROJECT],
        "can_be_delegated": False,
        "is_sensitive": True,
        "description": "Назначение role template сотруднику.",
    },
]


# Delegation rules — which scope transitions are allowed for each permission.
# Only permissions that are actually delegable (``can_be_delegated=True`` in
# the catalog) get entries here. Anything not listed falls back to "disallow".
CORE_DELEGATION_RULES: list[dict] = [
    # Projects-scope delegation (most common case)
    {"permission_code": "project.edit", "from_scope_type": SCOPE_COMPANY, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_narrower_scope": True, "max_delegate_depth": 2},
    {"permission_code": "project.assign_members", "from_scope_type": SCOPE_COMPANY, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_narrower_scope": True, "max_delegate_depth": 2},
    {"permission_code": "project.assign_rights", "from_scope_type": SCOPE_COMPANY, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_narrower_scope": True, "max_delegate_depth": 2},
    {"permission_code": "project.assign_rights", "from_scope_type": SCOPE_PROJECT, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_same_scope_only": True, "max_delegate_depth": 1},
    {"permission_code": "project.chat.moderate", "from_scope_type": SCOPE_PROJECT, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_same_scope_only": True, "max_delegate_depth": 1},

    # Documents — editable within the same scope or narrower
    {"permission_code": "docs.view", "from_scope_type": SCOPE_COMPANY, "to_scope_type": SCOPE_DEPARTMENT,
     "allow_delegate": True, "allow_narrower_scope": True, "max_delegate_depth": 2},
    {"permission_code": "docs.view", "from_scope_type": SCOPE_COMPANY, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_narrower_scope": True, "max_delegate_depth": 2},
    {"permission_code": "docs.upload", "from_scope_type": SCOPE_PROJECT, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_same_scope_only": True, "max_delegate_depth": 1},
    {"permission_code": "docs.edit", "from_scope_type": SCOPE_PROJECT, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_same_scope_only": True, "max_delegate_depth": 1},
    {"permission_code": "docs.delete", "from_scope_type": SCOPE_PROJECT, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_same_scope_only": True, "max_delegate_depth": 1},
    {"permission_code": "docs.assign_editors", "from_scope_type": SCOPE_PROJECT, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_same_scope_only": True, "max_delegate_depth": 1},

    {"permission_code": "project.docs.view", "from_scope_type": SCOPE_COMPANY, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_narrower_scope": True, "max_delegate_depth": 2},
    {"permission_code": "project.docs.upload", "from_scope_type": SCOPE_PROJECT, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_same_scope_only": True, "max_delegate_depth": 1},
    {"permission_code": "project.docs.edit", "from_scope_type": SCOPE_PROJECT, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_same_scope_only": True, "max_delegate_depth": 1},
    {"permission_code": "project.docs.assign_editors", "from_scope_type": SCOPE_PROJECT, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_same_scope_only": True, "max_delegate_depth": 1},

    # Tasks — same as documents
    {"permission_code": "tasks.view", "from_scope_type": SCOPE_COMPANY, "to_scope_type": SCOPE_DEPARTMENT,
     "allow_delegate": True, "allow_narrower_scope": True, "max_delegate_depth": 2},
    {"permission_code": "tasks.view", "from_scope_type": SCOPE_COMPANY, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_narrower_scope": True, "max_delegate_depth": 2},
    {"permission_code": "tasks.create", "from_scope_type": SCOPE_PROJECT, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_same_scope_only": True, "max_delegate_depth": 1},
    {"permission_code": "tasks.assign", "from_scope_type": SCOPE_PROJECT, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_same_scope_only": True, "max_delegate_depth": 1},
    {"permission_code": "tasks.edit", "from_scope_type": SCOPE_PROJECT, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_same_scope_only": True, "max_delegate_depth": 1},
    {"permission_code": "tasks.change_deadline", "from_scope_type": SCOPE_PROJECT, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_same_scope_only": True, "max_delegate_depth": 1},
    {"permission_code": "tasks.block", "from_scope_type": SCOPE_PROJECT, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_same_scope_only": True, "max_delegate_depth": 1},

    {"permission_code": "project.tasks.view", "from_scope_type": SCOPE_COMPANY, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_narrower_scope": True, "max_delegate_depth": 2},
    {"permission_code": "project.tasks.create", "from_scope_type": SCOPE_PROJECT, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_same_scope_only": True, "max_delegate_depth": 1},
    {"permission_code": "project.tasks.assign", "from_scope_type": SCOPE_PROJECT, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_same_scope_only": True, "max_delegate_depth": 1},
    {"permission_code": "project.tasks.edit", "from_scope_type": SCOPE_PROJECT, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_same_scope_only": True, "max_delegate_depth": 1},
    {"permission_code": "project.tasks.change_deadline", "from_scope_type": SCOPE_PROJECT, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_same_scope_only": True, "max_delegate_depth": 1},
    {"permission_code": "project.tasks.block", "from_scope_type": SCOPE_PROJECT, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_same_scope_only": True, "max_delegate_depth": 1},

    # AI chat
    {"permission_code": "ai.chat.use", "from_scope_type": SCOPE_COMPANY, "to_scope_type": SCOPE_SELF,
     "allow_delegate": True, "allow_narrower_scope": True, "max_delegate_depth": 1},

    # Rights management — narrowly delegable
    {"permission_code": "rights.grant", "from_scope_type": SCOPE_COMPANY, "to_scope_type": SCOPE_DEPARTMENT,
     "allow_delegate": True, "allow_narrower_scope": True, "max_delegate_depth": 1},
    {"permission_code": "rights.grant", "from_scope_type": SCOPE_COMPANY, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_narrower_scope": True, "max_delegate_depth": 1},
    {"permission_code": "rights.revoke", "from_scope_type": SCOPE_COMPANY, "to_scope_type": SCOPE_DEPARTMENT,
     "allow_delegate": True, "allow_narrower_scope": True, "max_delegate_depth": 1},
    {"permission_code": "rights.revoke", "from_scope_type": SCOPE_COMPANY, "to_scope_type": SCOPE_PROJECT,
     "allow_delegate": True, "allow_narrower_scope": True, "max_delegate_depth": 1},
]
# fmt: on


# ---------------------------------------------------------------------------
# Role templates (convenience bundles)
# ---------------------------------------------------------------------------


CORE_ROLE_TEMPLATES: list[dict] = [
    {
        "code": "employee_base",
        "name": "Базовый сотрудник",
        "description": "Минимальный набор для обычного сотрудника.",
        "default_scope_type": SCOPE_COMPANY,
        "permissions": [
            ("ai.chat.use", "use_only"),
            ("ai.models.select", "use_only"),
            ("docs.view", "use_only"),
        ],
    },
    {
        "code": "project_lead_base",
        "name": "Project Lead",
        "description": "Управление проектом, назначение участников и прав внутри него.",
        "default_scope_type": SCOPE_PROJECT,
        "permissions": [
            ("project.edit", "use_and_delegate"),
            ("project.assign_members", "use_and_delegate"),
            ("project.assign_rights", "use_and_delegate"),
            ("project.chat.moderate", "use_and_delegate"),
            ("docs.view", "use_and_delegate"),
            ("docs.upload", "use_and_delegate"),
            ("docs.edit", "use_and_delegate"),
            ("docs.assign_editors", "use_and_delegate"),
            ("tasks.create", "use_and_delegate"),
            ("tasks.assign", "use_and_delegate"),
            ("tasks.edit", "use_and_delegate"),
            ("tasks.change_deadline", "use_and_delegate"),
            ("tasks.block", "use_and_delegate"),
            ("ai.chat.use", "use_only"),
            ("ai.models.select", "use_only"),
        ],
    },
    {
        "code": "department_coordinator_base",
        "name": "Department Coordinator",
        "description": "Координация отдела: состав, документы, базовые операции.",
        "default_scope_type": SCOPE_DEPARTMENT,
        "permissions": [
            ("department.edit", "use_and_delegate"),
            ("department.assign_members", "use_and_delegate"),
            ("docs.view", "use_and_delegate"),
            ("docs.upload", "use_and_delegate"),
            ("docs.edit", "use_and_delegate"),
            ("tasks.create", "use_and_delegate"),
            ("tasks.assign", "use_and_delegate"),
        ],
    },
    {
        "code": "company_admin_base",
        "name": "Company Admin",
        "description": "Полный набор для администратора компании.",
        "default_scope_type": SCOPE_COMPANY,
        "permissions": [
            ("department.create", "use_only"),
            ("department.edit", "use_and_delegate"),
            ("department.assign_members", "use_and_delegate"),
            ("project.create", "use_only"),
            ("project.edit", "use_and_delegate"),
            ("project.assign_members", "use_and_delegate"),
            ("project.assign_rights", "use_and_delegate"),
            ("project.chat.moderate", "use_and_delegate"),
            ("docs.view", "use_and_delegate"),
            ("docs.upload", "use_and_delegate"),
            ("docs.edit", "use_and_delegate"),
            ("docs.delete", "use_and_delegate"),
            ("docs.assign_editors", "use_and_delegate"),
            ("tasks.create", "use_and_delegate"),
            ("tasks.assign", "use_and_delegate"),
            ("tasks.edit", "use_and_delegate"),
            ("tasks.change_deadline", "use_and_delegate"),
            ("tasks.block", "use_and_delegate"),
            ("ai.chat.use", "use_and_delegate"),
            ("ai.models.select", "use_and_delegate"),
            ("rights.grant", "use_and_delegate"),
            ("rights.revoke", "use_and_delegate"),
            ("roles.assign", "use_only"),
        ],
    },
]


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def _iter_summary(items: Iterable[tuple[str, bool]]) -> tuple[int, int]:
    created = updated = 0
    for _code, is_created in items:
        if is_created:
            created += 1
        else:
            updated += 1
    return created, updated


@transaction.atomic
def seed_permissions() -> tuple[int, int]:
    results: list[tuple[str, bool]] = []
    for raw in CORE_PERMISSIONS:
        defaults = {
            "name": raw["name"],
            "description": raw.get("description", ""),
            "module": raw["module"],
            "allowed_scopes": list(raw["allowed_scopes"]),
            "can_be_delegated": bool(raw.get("can_be_delegated", False)),
            "is_sensitive": bool(raw.get("is_sensitive", False)),
        }
        obj, created = PermissionDefinition.objects.update_or_create(
            code=raw["code"], defaults=defaults
        )
        if not created and not obj.is_active and raw.get("keep_active_flag", True):
            # Seeds never *revive* operator-deactivated permissions.
            pass
        results.append((raw["code"], created))
    return _iter_summary(results)


@transaction.atomic
def seed_delegation_rules() -> tuple[int, int]:
    results: list[tuple[str, bool]] = []
    for raw in CORE_DELEGATION_RULES:
        defaults = {
            "allow_delegate": bool(raw.get("allow_delegate", True)),
            "allow_same_scope_only": bool(raw.get("allow_same_scope_only", False)),
            "allow_narrower_scope": bool(raw.get("allow_narrower_scope", True)),
            "max_delegate_depth": int(raw.get("max_delegate_depth", 1)),
        }
        obj, created = DelegationRule.objects.update_or_create(
            permission_code=raw["permission_code"],
            from_scope_type=raw["from_scope_type"],
            to_scope_type=raw["to_scope_type"],
            defaults=defaults,
        )
        results.append((str(obj), created))
    return _iter_summary(results)


@transaction.atomic
def seed_role_templates() -> tuple[int, int]:
    results: list[tuple[str, bool]] = []
    for raw in CORE_ROLE_TEMPLATES:
        template, created = RoleTemplate.objects.update_or_create(
            code=raw["code"],
            defaults={
                "name": raw["name"],
                "description": raw.get("description", ""),
                "default_scope_type": raw.get("default_scope_type", SCOPE_GLOBAL),
                "is_system": True,
            },
        )
        results.append((template.code, created))

        desired_codes = {code for code, _mode in raw["permissions"]}
        for code, mode in raw["permissions"]:
            RoleTemplatePermission.objects.update_or_create(
                role_template=template,
                permission_code=code,
                defaults={"grant_mode": mode, "default_enabled": True},
            )
        # Remove permissions that are no longer part of the declared template.
        RoleTemplatePermission.objects.filter(role_template=template).exclude(
            permission_code__in=desired_codes
        ).delete()
    return _iter_summary(results)


def seed_all() -> dict[str, tuple[int, int]]:
    """Run every seed function. Returns created/updated counts per section."""

    return {
        "permissions": seed_permissions(),
        "delegation_rules": seed_delegation_rules(),
        "role_templates": seed_role_templates(),
    }
