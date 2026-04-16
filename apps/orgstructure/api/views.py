from django.db.models import Q
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.orgstructure.models import OrgUnit, OrgUnitMember

from .serializers import OrgUnitMemberSerializer, OrgUnitSerializer


class OrgUnitListView(generics.ListAPIView):
    queryset = OrgUnit.objects.select_related("organization", "parent")
    serializer_class = OrgUnitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = self.queryset.order_by("id")
        q = self.request.query_params.get("q")
        status = self.request.query_params.get("status")
        sort = self.request.query_params.get("sort")
        organization_id = self.request.query_params.get("organization_id")

        if organization_id:
            qs = qs.filter(organization_id=organization_id)

        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))

        if status == "active":
            qs = qs.filter(is_active=True)
        elif status == "inactive":
            qs = qs.filter(is_active=False)

        sort_map = {
            "name": "name",
            "-name": "-name",
            "created_at": "created_at",
            "-created_at": "-created_at",
            "id": "id",
            "-id": "-id",
        }
        if sort in sort_map:
            qs = qs.order_by(sort_map[sort])

        return qs


class OrgUnitDetailView(generics.RetrieveAPIView):
    queryset = OrgUnit.objects.select_related("organization", "parent")
    serializer_class = OrgUnitSerializer
    permission_classes = [IsAuthenticated]


class OrgUnitChildrenView(generics.ListAPIView):
    serializer_class = OrgUnitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return OrgUnit.objects.select_related("organization", "parent").filter(
            parent_id=self.kwargs["pk"]
        )


class OrgUnitMembersView(generics.ListAPIView):
    serializer_class = OrgUnitMemberSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return OrgUnitMember.objects.select_related("user", "org_unit").filter(
            org_unit_id=self.kwargs["pk"]
        )
