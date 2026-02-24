from __future__ import annotations

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "identity",
            "0008_merge_0002_orgmembership_legacy_columns_nullable_0007_personmessagethread_personmessage_personcontactentry_and_more",
        ),
    ]

    operations = [
        migrations.CreateModel(
            name="Client",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("name", models.CharField(max_length=200)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "org",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="clients",
                        to="identity.org",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["org", "name"], name="id_client_org_name_idx"),
                    models.Index(
                        fields=["org", "created_at"],
                        name="id_client_org_created_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("org", "name"), name="unique_client_name_per_org"
                    )
                ],
            },
        ),
    ]
