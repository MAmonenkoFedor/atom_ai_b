from django.urls import path

from .views import (
    OrgUnitChildrenView,
    OrgUnitDetailView,
    OrgUnitListView,
    OrgUnitMembersView,
)

urlpatterns = [
    path("units", OrgUnitListView.as_view(), name="org-units-list"),
    path("units/<int:pk>", OrgUnitDetailView.as_view(), name="org-units-detail"),
    path("units/<int:pk>/children", OrgUnitChildrenView.as_view(), name="org-units-children"),
    path("units/<int:pk>/members", OrgUnitMembersView.as_view(), name="org-units-members"),
]
