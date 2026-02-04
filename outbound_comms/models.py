from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class OutboundDraftType(models.TextChoices):
    EMAIL = "email", "Email"
    COMMENT = "comment", "Comment"


class OutboundDraftStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SENT = "sent", "Sent"


class OutboundWorkItemType(models.TextChoices):
    TASK = "task", "Task"
    EPIC = "epic", "Epic"


class OutboundDraft(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        "identity.Org",
        on_delete=models.CASCADE,
        related_name="outbound_drafts",
    )
    project = models.ForeignKey(
        "work_items.Project",
        on_delete=models.CASCADE,
        related_name="outbound_drafts",
    )
    type = models.CharField(max_length=20, choices=OutboundDraftType.choices)
    status = models.CharField(
        max_length=20, choices=OutboundDraftStatus.choices, default=OutboundDraftStatus.DRAFT
    )

    template = models.ForeignKey(
        "templates.Template",
        on_delete=models.PROTECT,
        related_name="outbound_drafts",
    )
    template_version = models.ForeignKey(
        "templates.TemplateVersion",
        on_delete=models.PROTECT,
        related_name="outbound_drafts",
    )

    subject = models.CharField(max_length=300, blank=True, default="")
    body_markdown = models.TextField()

    # Email drafts only.
    to_user_ids = models.JSONField(default=list, blank=True)

    # Comment drafts only.
    work_item_type = models.CharField(
        max_length=10, choices=OutboundWorkItemType.choices, null=True, blank=True
    )
    work_item_id = models.UUIDField(null=True, blank=True)
    comment_client_safe = models.BooleanField(default=False)
    sent_comment_id = models.UUIDField(null=True, blank=True)

    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_outbound_drafts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    sent_at = models.DateTimeField(null=True, blank=True)
    sent_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_outbound_drafts",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(type=OutboundDraftType.EMAIL, work_item_type__isnull=True)
                    | models.Q(type=OutboundDraftType.COMMENT, work_item_type__isnull=False)
                ),
                name="outbound_draft_work_item_required_for_comments",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "created_at"]),
            models.Index(fields=["org", "created_at"]),
            models.Index(fields=["project", "status", "created_at"]),
        ]
