import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orgstructure", "0001_initial"),
        ("chats", "0006_alter_chatattachment_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="chat",
            name="chat_scope",
            field=models.CharField(
                choices=[
                    ("personal", "Personal"),
                    ("department", "Department"),
                    ("project", "Project"),
                ],
                default="personal",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="chat",
            name="org_unit",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="chats",
                to="orgstructure.orgunit",
            ),
        ),
    ]

