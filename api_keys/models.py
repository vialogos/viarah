from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class ApiKey(models.Model):
    class Scope(models.TextChoices):
        READ = "read", "Read"
        WRITE = "write", "Write"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey("identity.Org", on_delete=models.CASCADE, related_name="api_keys")
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )

    # Optional restriction (stronger-than-membership) for automation use cases.
    project_id = models.UUIDField(null=True, blank=True)

    name = models.CharField(max_length=200)

    prefix = models.CharField(max_length=40, unique=True)
    secret_hash = models.CharField(max_length=128)
    scopes = models.JSONField(default=list, blank=True)

    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_api_keys",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    rotated_at = models.DateTimeField(null=True, blank=True)

    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["org", "created_at"]),
            models.Index(fields=["org", "revoked_at"]),
            models.Index(fields=["org", "owner_user", "created_at"]),
            models.Index(fields=["owner_user", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.org_id})"

    def clean(self):
        self.name = self.name.strip()
