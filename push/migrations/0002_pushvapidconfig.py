from __future__ import annotations

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("push", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PushVapidConfig",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("key", models.CharField(default="default", max_length=50, unique=True)),
                ("vapid_public_key", models.TextField(blank=True, default="")),
                ("vapid_private_key_ciphertext", models.TextField(blank=True, null=True)),
                ("vapid_subject", models.CharField(blank=True, default="", max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]

