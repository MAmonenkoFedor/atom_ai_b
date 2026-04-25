from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.db import transaction
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.api.permissions import IsCompanyAdminOrSuperAdmin, normalized_roles_for_user
from apps.organizations.models import OrganizationMember
from apps.orgstructure.models import OrgUnit, OrgUnitMember

from .serializers import (
    OrgUnitCreateSerializer,
    OrgUnitMemberSerializer,
    OrgUnitMemberUpsertSerializer,
    OrgUnitSerializer,
)


class OrgUnitListView(generics.ListCreateAPIView):
    queryset = OrgUnit.objects.select_related("organization", "parent")
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsCompanyAdminOrSuperAdmin()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return OrgUnitCreateSerializer
        return OrgUnitSerializer

    def get_queryset(self):
        qs = OrgUnit.objects.select_related("organization", "parent").order_by("id")
        roles = normalized_roles_for_user(self.request.user)
        if "super_admin" not in roles:
            org_ids = list(
                OrganizationMember.objects.filter(user=self.request.user, is_active=True).values_list(
                    "organization_id", flat=True
                )
            )
            if org_ids:
                qs = qs.filter(organization_id__in=org_ids)
            elif self.request.user.is_authenticated:
                qs = qs.none()

        q = self.request.query_params.get("q")
        status_param = self.request.query_params.get("status")
        sort = self.request.query_params.get("sort")
        organization_id = self.request.query_params.get("organization_id")

        if organization_id:
            qs = qs.filter(organization_id=organization_id)

        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))

        if status_param == "active":
            qs = qs.filter(is_active=True)
        elif status_param == "inactive":
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

    def perform_create(self, serializer):
        serializer.save(is_active=True)


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


class OrgUnitMembersView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsCompanyAdminOrSuperAdmin()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return OrgUnitMemberUpsertSerializer
        return OrgUnitMemberSerializer

    def get_queryset(self):
        return OrgUnitMember.objects.select_related("user", "org_unit").filter(
            org_unit_id=self.kwargs["pk"]
        )

    @staticmethod
    def _require_manage_org(user, organization_id: int) -> None:
        roles = normalized_roles_for_user(user)
        if "super_admin" in roles:
            return
        if "company_admin" not in roles:
            raise PermissionDenied()
        if not OrganizationMember.objects.filter(
            user=user, organization_id=organization_id, is_active=True
        ).exists():
            raise PermissionDenied()

    def create(self, request, *args, **kwargs):
        org_unit = get_object_or_404(OrgUnit.objects.select_related("organization"), pk=self.kwargs["pk"])
        self._require_manage_org(request.user, org_unit.organization_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        if not OrganizationMember.objects.filter(
            user=user, organization=org_unit.organization, is_active=True
        ).exists():
            raise ValidationError({"user": "Пользователь не в этой организации."})
        is_lead = serializer.validated_data.get("is_lead", False)
        position = serializer.validated_data.get("position", "") or ""
        with transaction.atomic():
            if is_lead:
                OrgUnitMember.objects.filter(org_unit=org_unit, is_lead=True).update(is_lead=False)
            member, _ = OrgUnitMember.objects.update_or_create(
                org_unit=org_unit,
                user=user,
                defaults={"is_lead": is_lead, "position": position},
            )
        out = OrgUnitMemberSerializer(member, context=self.get_serializer_context())
        return Response(out.data, status=status.HTTP_201_CREATED)
