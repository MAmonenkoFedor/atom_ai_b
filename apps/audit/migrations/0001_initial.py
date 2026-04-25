# Generated manually for audit events

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("actor_role", models.CharField(blank=True, max_length=64)),
                ("company_id", models.CharField(blank=True, max_length=64)),
                ("department_id", models.CharField(blank=True, max_length=64)),
                ("event_type", models.CharField(max_length=128)),
                ("entity_type", models.CharField(max_length=64)),
                ("entity_id", models.CharField(blank=True, max_length=128)),
                ("action", models.CharField(max_length=64)),
                ("project_id", models.CharField(blank=True, max_length=64)),
                ("task_id", models.CharField(blank=True, max_length=64)),
                ("chat_id", models.CharField(blank=True, max_length=64)),
                ("request_path", models.CharField(blank=True, max_length=512)),
                ("request_method", models.CharField(blank=True, max_length=16)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=512)),
                ("trace_id", models.CharField(blank=True, max_length=64)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at", "-id"),
            },
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=("created_at",), name="audit_audit_created_c93543_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=("actor", "created_at"), name="audit_audit_actor_i_fef507_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=("event_type", "created_at"), name="audit_audit_event_t_6c7f08_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=("project_id", "created_at"), name="audit_audit_project_4df4f4_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=("task_id", "created_at"), name="audit_audit_task_id_ae0a84_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=("chat_id", "created_at"), name="audit_audit_chat_id_1dc08f_idx"),
        ),
    ]
