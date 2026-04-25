# Generated manually for project lead flag (separate from role grants).

from django.db import migrations, models


def forwards_set_is_lead_from_role(apps, schema_editor):
    ProjectMember = apps.get_model("projects", "ProjectMember")
    seen = set()
    for m in (
        ProjectMember.objects.filter(role="lead", is_active=True)
        .order_by("project_id", "id")
        .iterator()
    ):
        pid = m.project_id
        if pid in seen:
            continue
        seen.add(pid)
        ProjectMember.objects.filter(pk=m.pk).update(is_lead=True)


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0008_projectmember_assignment_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectmember",
            name="is_lead",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(forwards_set_is_lead_from_role, backwards_noop),
    ]
