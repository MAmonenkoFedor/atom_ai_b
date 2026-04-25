from django.urls import path

from .super_admin_views import (
    CapabilityCatalogView,
    DisableUserView,
    EnableUserView,
    ForceLogoutUserView,
    InviteUserView,
    MyCapabilitiesView,
    PlatformUserDetailView,
    PlatformUsersListView,
    SetUserPasswordView,
    UpdateUserCapabilitiesView,
    UpdateUserRolesView,
)
from .super_admin_llm_views import (
    SuperAdminLlmProviderDetailView,
    SuperAdminLlmProviderProbeView,
    SuperAdminLlmProvidersListCreateView,
)
from .views import (
    AuthCsrfCookieView,
    AuthLoginView,
    AuthLogoutView,
    AuthSessionView,
    EmployeeDetailView,
    EmployeeListView,
    InviteActivateView,
    MePasswordChangeView,
    MeView,
)

urlpatterns = [
    path("auth/csrf", AuthCsrfCookieView.as_view(), name="auth-csrf-cookie"),
    path("me", MeView.as_view(), name="me"),
    path("me/password", MePasswordChangeView.as_view(), name="me-password"),
    path(
        "me/capabilities",
        MyCapabilitiesView.as_view(),
        name="me-capabilities",
    ),
    path("employees", EmployeeListView.as_view(), name="employees-list"),
    path("employees/<int:pk>", EmployeeDetailView.as_view(), name="employees-detail"),
    path("auth/login", AuthLoginView.as_view(), name="auth-login"),
    path("auth/logout", AuthLogoutView.as_view(), name="auth-logout"),
    path("auth/session", AuthSessionView.as_view(), name="auth-session"),
    path("auth/invite/activate", InviteActivateView.as_view(), name="auth-invite-activate"),
    path(
        "super-admin/users",
        PlatformUsersListView.as_view(),
        name="super-admin-users-list",
    ),
    path(
        "super-admin/users/<int:user_id>",
        PlatformUserDetailView.as_view(),
        name="super-admin-users-detail",
    ),
    path(
        "super-admin/users/invite",
        InviteUserView.as_view(),
        name="super-admin-users-invite",
    ),
    path(
        "super-admin/users/<int:user_id>/password",
        SetUserPasswordView.as_view(),
        name="super-admin-users-password",
    ),
    path(
        "super-admin/users/<int:user_id>/disable",
        DisableUserView.as_view(),
        name="super-admin-users-disable",
    ),
    path(
        "super-admin/users/<int:user_id>/enable",
        EnableUserView.as_view(),
        name="super-admin-users-enable",
    ),
    path(
        "super-admin/users/<int:user_id>/force-logout",
        ForceLogoutUserView.as_view(),
        name="super-admin-users-force-logout",
    ),
    path(
        "super-admin/users/<int:user_id>/roles",
        UpdateUserRolesView.as_view(),
        name="super-admin-users-roles",
    ),
    path(
        "super-admin/users/<int:user_id>/capabilities",
        UpdateUserCapabilitiesView.as_view(),
        name="super-admin-users-capabilities",
    ),
    path(
        "super-admin/capabilities",
        CapabilityCatalogView.as_view(),
        name="super-admin-capability-catalog",
    ),
    path(
        "super-admin/llm/providers",
        SuperAdminLlmProvidersListCreateView.as_view(),
        name="super-admin-llm-providers",
    ),
    path(
        "super-admin/llm/providers/<int:provider_id>",
        SuperAdminLlmProviderDetailView.as_view(),
        name="super-admin-llm-provider-detail",
    ),
    path(
        "super-admin/llm/providers/<int:provider_id>/probe",
        SuperAdminLlmProviderProbeView.as_view(),
        name="super-admin-llm-provider-probe",
    ),
]
