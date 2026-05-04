# Generated manually for P1.1 project PATCH split (public summary, dates, JSON settings).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0010_remove_projectresourcerequest_projects_pr_stat_created_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="public_summary",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="project",
            name="planned_start",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="project",
            name="planned_end",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="project",
            name="project_settings",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
