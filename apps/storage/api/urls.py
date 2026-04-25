from django.urls import path

from .provider_views import (
    SuperAdminStorageProviderDetailView,
    SuperAdminStorageProviderProbeView,
    SuperAdminStorageProvidersListCreateView,
)
from .views import StorageQuotaDetailView, StorageQuotaListCreateView, StorageUsageView

urlpatterns = [
    path("super-admin/storage/usage", StorageUsageView.as_view(), name="super-admin-storage-usage"),
    path(
        "super-admin/storage/quotas",
        StorageQuotaListCreateView.as_view(),
        name="super-admin-storage-quotas",
    ),
    path(
        "super-admin/storage/quotas/<int:quota_id>",
        StorageQuotaDetailView.as_view(),
        name="super-admin-storage-quota-detail",
    ),
    path(
        "super-admin/storage/providers",
        SuperAdminStorageProvidersListCreateView.as_view(),
        name="super-admin-storage-providers",
    ),
    path(
        "super-admin/storage/providers/<int:provider_id>",
        SuperAdminStorageProviderDetailView.as_view(),
        name="super-admin-storage-provider-detail",
    ),
    path(
        "super-admin/storage/providers/<int:provider_id>/probe",
        SuperAdminStorageProviderProbeView.as_view(),
        name="super-admin-storage-provider-probe",
    ),
]
