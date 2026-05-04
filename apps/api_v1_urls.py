from django.urls import include, path

urlpatterns = [
    path("core/", include("apps.core.api.urls")),
    path("", include("apps.core.api.parallel_contract_urls")),
    path("", include("apps.orgstructure.api.employee_urls")),
    path("", include("apps.workspaces.api.urls")),
    path("", include("apps.identity.api.urls")),
    path("org/", include("apps.orgstructure.api.urls")),
    path("", include("apps.orgstructure.api.department_urls")),
    path("", include("apps.projects.api.urls")),
    path("", include("apps.chats.api.urls")),
    path("", include("apps.ai.api.urls")),
    path("", include("apps.audit.api.urls")),
    path("", include("apps.storage.api.urls")),
    path("access/", include("apps.access.api.urls")),
]
