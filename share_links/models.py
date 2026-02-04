from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class ShareLink(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey("identity.Org", on_delete=models.CASCADE, related_name="share_links")
    report_run = models.ForeignKey(
        "reports.ReportRun", on_delete=models.CASCADE, related_name="share_links"
    )

    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_share_links",
    )
    created_by_api_key = models.ForeignKey(
        "api_keys.ApiKey",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_share_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    output_markdown = models.TextField(blank=True)
    output_html = models.TextField(blank=True)

    last_access_at = models.DateTimeField(null=True, blank=True)
    access_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(created_by_user__isnull=False, created_by_api_key__isnull=True)
                    | models.Q(created_by_user__isnull=True, created_by_api_key__isnull=False)
                ),
                name="share_links_created_by_xor",
            )
        ]
        indexes = [
            models.Index(fields=["org", "created_at"]),
            models.Index(fields=["org", "report_run", "created_at"]),
            models.Index(fields=["token_hash"]),
            models.Index(fields=["org", "report_run", "revoked_at"]),
            models.Index(fields=["org", "report_run", "expires_at"]),
        ]

    def __str__(self) -> str:
        return f"ShareLink ({self.report_run_id})"


class ShareLinkAccessLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    share_link = models.ForeignKey(ShareLink, on_delete=models.CASCADE, related_name="access_logs")
    accessed_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["share_link", "accessed_at"]),
        ]

    def __str__(self) -> str:
        return f"ShareLinkAccessLog ({self.share_link_id})"
