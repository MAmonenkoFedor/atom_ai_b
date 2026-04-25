# Generated manually for ProjectDocument

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils.text import get_valid_filename


def _project_document_upload_to(instance, filename: str) -> str:
    safe = get_valid_filename(filename)
    return f"project_documents/{instance.project_id}/{uuid.uuid4().hex[:10]}_{safe}"


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("projects", "0003_project_org_unit_and_member_engagement"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProjectDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=500)),
                ("document_type", models.CharField(max_length=16)),
                (
                    "source",
                    models.CharField(
                        choices=[("upload", "Upload"), ("external", "External link")],
                        max_length=16,
                    ),
                ),
                ("external_href", models.TextField(blank=True)),
                (
                    "file",
                    models.FileField(
                        blank=True,
                        null=True,
                        upload_to=_project_document_upload_to,
                    ),
                ),
                ("owner_label", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="projects.project",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="uploaded_project_documents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-updated_at",),
            },
        ),
    ]
