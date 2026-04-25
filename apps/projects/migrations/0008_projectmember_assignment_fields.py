from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0007_projectresourcerequest"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="projectmember",
            name="role",
            field=models.CharField(
                choices=[
                    ("owner", "Owner"),
                    ("lead", "Project lead"),
                    ("manager", "Project manager"),
                    ("editor", "Editor"),
                    ("contributor", "Contributor"),
                    ("viewer", "Viewer"),
                ],
                default="editor",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="projectmember",
            name="title_in_project",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="projectmember",
            name="assigned_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_project_members",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
