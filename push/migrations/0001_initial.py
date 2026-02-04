from __future__ import annotations

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PushSubscription",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("endpoint", models.TextField()),
                ("p256dh", models.CharField(max_length=256)),
                ("auth", models.CharField(max_length=128)),
                ("expiration_time", models.BigIntegerField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, default="", max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="push_subscriptions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="pushsubscription",
            constraint=models.UniqueConstraint(
                fields=("user", "endpoint"), name="unique_push_subscription_per_user_endpoint"
            ),
        ),
        migrations.AddIndex(
            model_name="pushsubscription",
            index=models.Index(fields=["user", "created_at"], name="push_user_created_at_idx"),
        ),
    ]
