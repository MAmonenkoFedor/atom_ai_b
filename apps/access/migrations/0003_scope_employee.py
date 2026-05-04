# Generated manually for employee-scope expansion.

from django.db import migrations, models


SCOPE_CHOICES = [
    ("global", "Global"),
    ("company", "Company"),
    ("department", "Department"),
    ("employee", "Employee"),
    ("project", "Project"),
    ("task", "Task"),
    ("ai_workspace", "AI workspace"),
    ("module", "Module"),
    ("self", "Self"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("access", "0002_permissiondeny_and_scope_expansion"),
    ]

    operations = [
        migrations.AlterField(
            model_name="delegationrule",
            name="from_scope_type",
            field=models.CharField(choices=SCOPE_CHOICES, max_length=32),
        ),
        migrations.AlterField(
            model_name="delegationrule",
            name="to_scope_type",
            field=models.CharField(choices=SCOPE_CHOICES, max_length=32),
        ),
        migrations.AlterField(
            model_name="permissiongrant",
            name="scope_type",
            field=models.CharField(choices=SCOPE_CHOICES, default="global", max_length=32),
        ),
        migrations.AlterField(
            model_name="roletemplate",
            name="default_scope_type",
            field=models.CharField(choices=SCOPE_CHOICES, default="global", max_length=32),
        ),
        migrations.AlterField(
            model_name="roletemplateassignment",
            name="scope_type",
            field=models.CharField(choices=SCOPE_CHOICES, default="global", max_length=32),
        ),
        migrations.AlterField(
            model_name="permissiondeny",
            name="scope_type",
            field=models.CharField(choices=SCOPE_CHOICES, default="global", max_length=32),
        ),
    ]
