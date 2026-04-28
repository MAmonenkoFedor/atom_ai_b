from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chats", "0003_alter_chat_project"),
    ]

    operations = [
        migrations.AddField(
            model_name="chat",
            name="chat_type",
            field=models.CharField(
                choices=[("general", "General"), ("project", "Project")],
                default="general",
                max_length=32,
            ),
        ),
    ]

