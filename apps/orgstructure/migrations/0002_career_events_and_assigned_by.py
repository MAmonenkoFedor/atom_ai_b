from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0001_initial"),
        ("orgstructure", "0001_initial"),
        ("projects", "0007_projectresourcerequest"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="orgunitmember",
            name="assigned_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_org_unit_members",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name="EmployeeCareerEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(
                    choices=[
                        ("hired", "Hired"),
                        ("system_role_changed", "System role changed"),
                        ("job_title_changed", "Job title changed"),
                        ("joined_department", "Joined department"),
                        ("left_department", "Left department"),
                        ("transferred_department", "Transferred department"),
                        ("became_department_lead", "Became department lead"),
                        ("removed_as_department_lead", "Removed as department lead"),
                        ("position_changed", "Position changed"),
                        ("assigned_to_project", "Assigned to project"),
                        ("removed_from_project", "Removed from project"),
                        ("project_role_changed", "Project role changed"),
                        ("became_project_lead", "Became project lead"),
                        ("removed_as_project_lead", "Removed as project lead"),
                        ("manager_changed", "Manager changed"),
                    ],
                    max_length=64,
                )),
                ("from_value", models.CharField(blank=True, max_length=255)),
                ("to_value", models.CharField(blank=True, max_length=255)),
                ("effective_from", models.DateTimeField()),
                ("effective_to", models.DateTimeField(blank=True, null=True)),
                ("reason", models.CharField(blank=True, max_length=500)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("employee", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="career_events",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("actor", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="authored_career_events",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("organization", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="career_events",
                    to="organizations.organization",
                )),
                ("project", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="employee_career_events",
                    to="projects.project",
                )),
                ("org_unit", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="employee_career_events",
                    to="orgstructure.orgunit",
                )),
            ],
            options={
                "ordering": ("-effective_from", "-id"),
            },
        ),
        migrations.AddIndex(
            model_name="employeecareerevent",
            index=models.Index(fields=["employee", "-effective_from"], name="orgstruct_career_emp_idx"),
        ),
        migrations.AddIndex(
            model_name="employeecareerevent",
            index=models.Index(fields=["event_type", "-effective_from"], name="orgstruct_career_evt_idx"),
        ),
        migrations.AddIndex(
            model_name="employeecareerevent",
            index=models.Index(fields=["project", "-effective_from"], name="orgstruct_career_proj_idx"),
        ),
        migrations.AddIndex(
            model_name="employeecareerevent",
            index=models.Index(fields=["org_unit", "-effective_from"], name="orgstruct_career_ou_idx"),
        ),
    ]
