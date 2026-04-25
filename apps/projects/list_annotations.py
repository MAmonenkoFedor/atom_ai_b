"""Аннотации для списка/детали проекта — без N+1 в сериализаторе."""

from __future__ import annotations

from django.db.models import CharField, Count, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce

from apps.chats.models import Chat
from apps.projects.models import Project, ProjectDocument, ProjectMember
from apps.projects.project_permissions import apply_project_list_visibility


def base_project_queryset():
    return Project.objects.select_related("organization", "created_by", "primary_org_unit")


def projects_queryset_with_annotations(user):
    """Базовый queryset проектов с аннотациями (для одного объекта через .get(pk=…))."""
    return annotate_for_project_list(apply_project_list_visibility(base_project_queryset(), user), user)


def annotate_for_project_list(qs, user):
    """
    Добавляет на каждую строку Project:
    - _documents_total — число ProjectDocument;
    - _chats_total — число Chat;
    - _my_project_role — роль текущего пользователя в команде или NULL.
    """
    docs_sq = (
        ProjectDocument.objects.filter(project_id=OuterRef("pk"))
        .values("project_id")
        .annotate(c=Count("id"))
        .values("c")[:1]
    )
    chats_sq = (
        Chat.objects.filter(project_id=OuterRef("pk"))
        .values("project_id")
        .annotate(c=Count("id"))
        .values("c")[:1]
    )
    role_sq = (
        ProjectMember.objects.filter(
            project_id=OuterRef("pk"),
            user_id=user.pk,
            is_active=True,
        )
        .values("role")[:1]
    )
    return qs.annotate(
        _documents_total=Coalesce(Subquery(docs_sq, output_field=IntegerField()), 0),
        _chats_total=Coalesce(Subquery(chats_sq, output_field=IntegerField()), 0),
        _my_project_role=Subquery(role_sq, output_field=CharField(max_length=32)),
    )
