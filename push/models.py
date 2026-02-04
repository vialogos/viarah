from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class PushSubscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.TextField()
    p256dh = models.CharField(max_length=256)
    auth = models.CharField(max_length=128)
    expiration_time = models.BigIntegerField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "endpoint"],
                name="unique_push_subscription_per_user_endpoint",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "created_at"], name="push_user_created_at_idx"),
        ]
