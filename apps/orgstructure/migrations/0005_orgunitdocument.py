# Generated manually — department workspace documents.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orgstructure", "0004_rename_orgstruct_career_emp_idx_orgstructur_employe_0076b5_idx_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("storage", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrgUnitDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=500)),
                ("document_type", models.CharField(max_length=16)),
                ("source", models.CharField(choices=[("upload", "Upload"), ("external", "External link")], max_length=16)),
                ("external_href", models.TextField(blank=True)),
                ("file", models.FileField(blank=True, null=True, upload_to="org_unit_documents/%Y/%m/")),
                ("storage_object_key", models.TextField(blank=True, default="")),
                ("upload_stored_bytes", models.PositiveBigIntegerField(default=0)),
                ("owner_label", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "org_unit",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="orgstructure.orgunit",
                    ),
                ),
                (
                    "storage_provider",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="org_unit_documents",
                        to="storage.storageprovider",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="uploaded_org_unit_documents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-updated_at",),
            },
        ),
    ]
