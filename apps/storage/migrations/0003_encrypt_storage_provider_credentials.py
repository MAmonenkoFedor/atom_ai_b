# Generated manually — encrypt legacy plaintext credentials at rest.

from django.db import migrations


def encrypt_provider_credentials(apps, schema_editor):
    StorageProvider = apps.get_model("storage", "StorageProvider")
    from apps.storage.credentials_vault import decrypt_credentials_field, encrypt_credentials_field

    for p in StorageProvider.objects.iterator():
        raw = p.credentials
        if isinstance(raw, dict) and raw.get("v") == 1 and raw.get("ct"):
            continue
        plain = decrypt_credentials_field(raw)
        if not plain.get("access_key") and not plain.get("secret_key"):
            continue
        StorageProvider.objects.filter(pk=p.pk).update(
            credentials=encrypt_credentials_field(plain["access_key"], plain["secret_key"]),
        )


class Migration(migrations.Migration):

    dependencies = [
        ("storage", "0002_storageprovider"),
    ]

    operations = [
        migrations.RunPython(encrypt_provider_credentials, migrations.RunPython.noop),
    ]
