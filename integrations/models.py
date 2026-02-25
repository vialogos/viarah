from __future__ import annotations

import uuid

from django.db import models


class OrgGitLabIntegration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.OneToOneField("identity.Org", on_delete=models.CASCADE, related_name="gitlab")

    base_url = models.URLField(max_length=500)
    token_ciphertext = models.TextField(blank=True, null=True)
    token_set_at = models.DateTimeField(blank=True, null=True)
    token_rotated_at = models.DateTimeField(blank=True, null=True)

    webhook_secret_hash = models.CharField(max_length=64, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["org", "updated_at"]),
        ]


class GlobalGitLabIntegration(models.Model):
    """Instance-wide GitLab integration defaults (used when org overrides are unset)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=50, unique=True, default="default")

    base_url = models.URLField(max_length=500, blank=True, default="")
    token_ciphertext = models.TextField(blank=True, null=True)
    token_set_at = models.DateTimeField(blank=True, null=True)
    token_rotated_at = models.DateTimeField(blank=True, null=True)

    webhook_secret_hash = models.CharField(max_length=64, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["key", "updated_at"]),
        ]


class TaskGitLabLink(models.Model):
    class GitLabType(models.TextChoices):
        ISSUE = "issue", "Issue"
        MERGE_REQUEST = "mr", "Merge Request"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(
        "work_items.Task", on_delete=models.CASCADE, related_name="gitlab_links"
    )

    web_url = models.URLField(max_length=1000)
    project_path = models.CharField(max_length=500)
    gitlab_type = models.CharField(max_length=20, choices=GitLabType.choices)
    gitlab_iid = models.PositiveIntegerField()

    cached_title = models.CharField(max_length=500, blank=True, default="")
    cached_state = models.CharField(max_length=50, blank=True, default="")
    cached_labels = models.JSONField(default=list, blank=True)
    cached_assignees = models.JSONField(default=list, blank=True)
    cached_participants = models.JSONField(default=list, blank=True)
    last_synced_at = models.DateTimeField(blank=True, null=True)

    last_sync_attempt_at = models.DateTimeField(blank=True, null=True)
    last_sync_error_code = models.CharField(max_length=100, blank=True, default="")
    last_sync_error_at = models.DateTimeField(blank=True, null=True)
    rate_limited_until = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["task", "web_url"], name="unique_task_gitlab_link_url"),
        ]
        indexes = [
            models.Index(fields=["task", "created_at"]),
            models.Index(fields=["project_path", "gitlab_type", "gitlab_iid"]),
        ]


class GitLabWebhookDelivery(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        "identity.Org", on_delete=models.CASCADE, related_name="gitlab_webhooks"
    )

    event_uuid = models.CharField(max_length=64, blank=True, null=True)
    event_type = models.CharField(max_length=100, blank=True, default="")
    project_path = models.CharField(max_length=500, blank=True, default="")
    gitlab_type = models.CharField(max_length=20, blank=True, default="")
    gitlab_iid = models.PositiveIntegerField(blank=True, null=True)
    payload_sha256 = models.CharField(max_length=64)

    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["org", "received_at"]),
            models.Index(fields=["event_uuid"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "event_uuid"],
                name="unique_org_gitlab_webhook_event_uuid",
                condition=models.Q(event_uuid__isnull=False),
            ),
        ]
