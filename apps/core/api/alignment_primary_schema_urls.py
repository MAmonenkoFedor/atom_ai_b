from django.urls import include, path

urlpatterns = [
    path("", include("apps.core.api.urls_auth_workspace")),
    path("", include("apps.core.api.urls_projects")),
    path("", include("apps.core.api.urls_company_admin")),
    path("", include("apps.core.api.urls_platform_admin")),
    path("", include("apps.core.api.urls_tasks")),
]
