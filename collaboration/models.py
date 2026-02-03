from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


def attachment_upload_to(instance: "Attachment", filename: str) -> str:
    del filename

    if instance.task_id:
        target_type = "task"
        target_id = instance.task_id
    elif instance.epic_id:
        target_type = "epic"
        target_id = instance.epic_id
    else:
        target_type = "unknown"
        target_id = "unknown"

    return f"attachments/{instance.org_id}/{target_type}/{target_id}/{instance.id}"


class Comment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey("identity.Org", on_delete=models.CASCADE, related_name="comments")
    author_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="authored_comments"
    )
    task = models.ForeignKey(
        "work_items.Task",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    epic = models.ForeignKey(
        "work_items.Epic",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    body_markdown = models.TextField()
    body_html = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(task__isnull=False, epic__isnull=True)
                    | models.Q(task__isnull=True, epic__isnull=False)
                ),
                name="comment_exactly_one_target",
            ),
        ]
        indexes = [
            models.Index(fields=["org", "created_at"]),
            models.Index(fields=["task", "created_at"]),
            models.Index(fields=["epic", "created_at"]),
        ]

    def __str__(self) -> str:
        target = self.task_id or self.epic_id
        return f"Comment {self.id} on {target}"


class Attachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey("identity.Org", on_delete=models.CASCADE, related_name="attachments")
    uploader_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="uploaded_attachments"
    )
    task = models.ForeignKey(
        "work_items.Task",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    epic = models.ForeignKey(
        "work_items.Epic",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    comment = models.ForeignKey(
        Comment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attachments",
    )
    file = models.FileField(upload_to=attachment_upload_to, max_length=500)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=200, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(task__isnull=False, epic__isnull=True)
                    | models.Q(task__isnull=True, epic__isnull=False)
                ),
                name="attachment_exactly_one_target",
            ),
        ]
        indexes = [
            models.Index(fields=["org", "created_at"]),
            models.Index(fields=["task", "created_at"]),
            models.Index(fields=["epic", "created_at"]),
            models.Index(fields=["comment", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Attachment {self.id} ({self.original_filename})"
