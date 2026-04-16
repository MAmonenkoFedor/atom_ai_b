from django.urls import include, path

urlpatterns = [
    path("api/", include("apps.core.api.alignment_primary_schema_urls")),
]
