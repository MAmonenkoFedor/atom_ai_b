"""URL routes for the access-control service."""

from __future__ import annotations

from django.urls import path

from .views import (
    DelegationRuleDetailView,
    DelegationRulesView,
    EmployeeEffectivePermissionsView,
    EmployeeGrantsView,
    EmployeePermissionAuditView,
    EmployeeTemplateDetailView,
    EmployeeTemplatesView,
    GrantRevokeView,
    GrantsView,
    PermissionDefinitionDetailView,
    PermissionsCatalogView,
    RoleTemplateDetailView,
    RoleTemplatePermissionsView,
    RoleTemplatesView,
)

urlpatterns = [
    # Catalog
    path("permissions", PermissionsCatalogView.as_view(), name="access-permissions"),
    path(
        "permissions/<int:pk>",
        PermissionDefinitionDetailView.as_view(),
        name="access-permission-detail",
    ),
    # Role templates
    path("role-templates", RoleTemplatesView.as_view(), name="access-role-templates"),
    path(
        "role-templates/<int:pk>",
        RoleTemplateDetailView.as_view(),
        name="access-role-template-detail",
    ),
    path(
        "role-templates/<int:pk>/permissions",
        RoleTemplatePermissionsView.as_view(),
        name="access-role-template-permissions",
    ),
    # Grants
    path("grants", GrantsView.as_view(), name="access-grants"),
    path("grants/<int:pk>/revoke", GrantRevokeView.as_view(), name="access-grant-revoke"),
    # Employee-scoped
    path(
        "employees/<int:employee_id>/grants",
        EmployeeGrantsView.as_view(),
        name="access-employee-grants",
    ),
    path(
        "employees/<int:employee_id>/effective-permissions",
        EmployeeEffectivePermissionsView.as_view(),
        name="access-employee-effective",
    ),
    path(
        "employees/<int:employee_id>/templates",
        EmployeeTemplatesView.as_view(),
        name="access-employee-templates",
    ),
    path(
        "employees/<int:employee_id>/templates/<int:assignment_id>",
        EmployeeTemplateDetailView.as_view(),
        name="access-employee-template-detail",
    ),
    path(
        "employees/<int:employee_id>/audit",
        EmployeePermissionAuditView.as_view(),
        name="access-employee-audit",
    ),
    # Delegation rules
    path("delegation-rules", DelegationRulesView.as_view(), name="access-delegation-rules"),
    path(
        "delegation-rules/<int:pk>",
        DelegationRuleDetailView.as_view(),
        name="access-delegation-rule-detail",
    ),
]
