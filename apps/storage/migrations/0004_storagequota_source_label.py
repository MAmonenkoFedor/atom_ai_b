# Generated manually — stable UI label + backfill.

from django.db import migrations, models


def backfill_source_labels(apps, schema_editor):
    from apps.storage.quota_labels import build_storage_quota_source_label

    StorageQuota = apps.get_model("storage", "StorageQuota")
    for row in StorageQuota.objects.all().iterator(chunk_size=200):
        if (getattr(row, "source_label", "") or "").strip():
            continue
        label = build_storage_quota_source_label(row.scope, row.scope_id or "")
        StorageQuota.objects.filter(pk=row.pk).update(source_label=label)


class Migration(migrations.Migration):

    dependencies = [
        ("storage", "0003_encrypt_storage_provider_credentials"),
    ]

    operations = [
        migrations.AddField(
            model_name="storagequota",
            name="source_label",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Stable UI label, e.g. «Платформа», «Организация: Acme» (not parsed from scope).",
                max_length=255,
            ),
        ),
        migrations.RunPython(backfill_source_labels, migrations.RunPython.noop),
    ]
