import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserCapability",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("capability", models.CharField(max_length=128)),
                ("scope", models.CharField(default="global", max_length=128)),
                ("reason", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "granted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="granted_capabilities",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="capability_grants",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddConstraint(
            model_name="usercapability",
            constraint=models.UniqueConstraint(
                fields=("user", "capability", "scope"),
                name="uniq_user_capability_per_scope",
            ),
        ),
        migrations.AddIndex(
            model_name="usercapability",
            index=models.Index(
                fields=["user", "capability"], name="identity_us_user_id_cap_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="usercapability",
            index=models.Index(
                fields=["capability"], name="identity_us_capabil_idx"
            ),
        ),
    ]
