from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class NotificationEventType(models.TextChoices):
    ASSIGNMENT_CHANGED = "assignment.changed", "Assignment changed"
    STATUS_CHANGED = "status.changed", "Status changed"
    COMMENT_CREATED = "comment.created", "Comment created"
    REPORT_PUBLISHED = "report.published", "Report published"


class NotificationChannel(models.TextChoices):
    IN_APP = "in_app", "In app"
    EMAIL = "email", "Email"
    PUSH = "push", "Push"


class EmailDeliveryStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    SUCCESS = "success", "Success"
    FAILURE = "failure", "Failure"


class NotificationEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        "identity.Org",
        on_delete=models.CASCADE,
        related_name="notification_events",
    )
    project = models.ForeignKey(
        "work_items.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notification_events",
    )
    event_type = models.CharField(max_length=100, choices=NotificationEventType.choices)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="authored_notification_events",
    )
    data_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["org", "created_at"]),
            models.Index(fields=["org", "event_type", "created_at"]),
            models.Index(fields=["project", "created_at"]),
        ]


class InAppNotification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        "identity.Org",
        on_delete=models.CASCADE,
        related_name="in_app_notifications",
    )
    project = models.ForeignKey(
        "work_items.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="in_app_notifications",
    )
    event = models.ForeignKey(
        NotificationEvent, on_delete=models.CASCADE, related_name="in_app_notifications"
    )
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="in_app_notifications",
    )
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "recipient_user"],
                name="unique_in_app_notification_per_event_recipient",
            ),
        ]
        indexes = [
            models.Index(fields=["recipient_user", "created_at"]),
            models.Index(fields=["recipient_user", "project", "created_at"]),
            models.Index(fields=["recipient_user", "read_at", "created_at"]),
        ]


class NotificationPreference(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        "identity.Org",
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    project = models.ForeignKey(
        "work_items.Project",
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    event_type = models.CharField(max_length=100, choices=NotificationEventType.choices)
    channel = models.CharField(max_length=20, choices=NotificationChannel.choices)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "project", "event_type", "channel"],
                name="unique_notification_preference_per_user_project_event_channel",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "project"]),
            models.Index(fields=["project", "event_type", "channel"]),
        ]


class ProjectNotificationSetting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        "identity.Org",
        on_delete=models.CASCADE,
        related_name="project_notification_settings",
    )
    project = models.ForeignKey(
        "work_items.Project",
        on_delete=models.CASCADE,
        related_name="notification_settings",
    )
    event_type = models.CharField(max_length=100, choices=NotificationEventType.choices)
    channel = models.CharField(max_length=20, choices=NotificationChannel.choices)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "event_type", "channel"],
                name="unique_project_notification_setting_per_project_event_channel",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "event_type", "channel"]),
        ]


class EmailDeliveryLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        "identity.Org",
        on_delete=models.CASCADE,
        related_name="email_deliveries",
    )
    project = models.ForeignKey(
        "work_items.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="email_deliveries",
    )
    notification_event = models.ForeignKey(
        NotificationEvent,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="email_deliveries",
    )
    outbound_draft = models.ForeignKey(
        "outbound_comms.OutboundDraft",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="email_deliveries",
    )
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="email_deliveries",
    )
    to_email = models.EmailField(blank=True, default="")
    subject = models.CharField(max_length=500, blank=True, default="")
    status = models.CharField(
        max_length=20, choices=EmailDeliveryStatus.choices, default=EmailDeliveryStatus.QUEUED
    )
    attempt_number = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=100, blank=True, default="")
    error_detail = models.TextField(blank=True, default="")
    queued_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(notification_event__isnull=False, outbound_draft__isnull=True)
                    | models.Q(notification_event__isnull=True, outbound_draft__isnull=False)
                ),
                name="email_delivery_exactly_one_source",
            ),
        ]
        indexes = [
            models.Index(fields=["org", "queued_at"]),
            models.Index(fields=["project", "queued_at"]),
            models.Index(fields=["project", "status", "queued_at"]),
        ]
