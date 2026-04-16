from django.urls import path

from .views import (
    AuthLoginView,
    AuthLogoutView,
    AuthSessionView,
    EmployeeDetailView,
    EmployeeListView,
    InviteActivateView,
    MeView,
)

urlpatterns = [
    path("me", MeView.as_view(), name="me"),
    path("employees", EmployeeListView.as_view(), name="employees-list"),
    path("employees/<int:pk>", EmployeeDetailView.as_view(), name="employees-detail"),
    path("auth/login", AuthLoginView.as_view(), name="auth-login"),
    path("auth/logout", AuthLogoutView.as_view(), name="auth-logout"),
    path("auth/session", AuthSessionView.as_view(), name="auth-session"),
    path("auth/invite/activate", InviteActivateView.as_view(), name="auth-invite-activate"),
]
