import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Allow ad-hoc AI chats that are not tied to a project."""

    dependencies = [
        ("chats", "0002_initial"),
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="chat",
            name="project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="chats",
                to="projects.project",
            ),
        ),
    ]
