from django.db import migrations, models

import apps.chats.models


class Migration(migrations.Migration):
    dependencies = [
        ("chats", "0005_merge_0004_chat_type_0004_chatattachment"),
    ]

    operations = [
        migrations.AlterField(
            model_name="chatattachment",
            name="file",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to=apps.chats.models.chat_attachment_upload_to,
            ),
        ),
    ]

