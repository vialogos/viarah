from __future__ import annotations

from django.db import migrations
from django.db.models import F


def forwards(apps, schema_editor):
    del schema_editor

    ApiKey = apps.get_model("api_keys", "ApiKey")

    ApiKey.objects.filter(
        owner_user_id__isnull=True,
        created_by_user_id__isnull=False,
    ).update(owner_user_id=F("created_by_user_id"))


def backwards(apps, schema_editor):
    del apps, schema_editor


class Migration(migrations.Migration):
    dependencies = [
        ("api_keys", "0002_apikey_expires_at_apikey_last_used_at_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
