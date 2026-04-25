from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", include("apps.core.api.urls")),
    path("api/v1/", include("apps.api_v1_urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path(
        "api/alignment/schema/",
        SpectacularAPIView.as_view(urlconf="config.alignment_schema_urls"),
        name="api-alignment-schema",
    ),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="api-schema"),
        name="api-docs",
    ),
    path(
        "api/alignment/docs/",
        SpectacularSwaggerView.as_view(url_name="api-alignment-schema"),
        name="api-alignment-docs",
    ),
    path("api/", include("apps.api_v1_urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
