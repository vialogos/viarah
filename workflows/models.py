from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class WorkflowStageCategory(models.TextChoices):
    BACKLOG = "backlog", "Backlog"
    IN_PROGRESS = "in_progress", "In progress"
    QA = "qa", "QA"
    DONE = "done", "Done"


class Workflow(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey("identity.Org", on_delete=models.CASCADE, related_name="workflows")
    name = models.CharField(max_length=200)
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_workflows",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["org", "created_at"]),
            models.Index(fields=["org", "updated_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.org_id})"


class WorkflowStage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="stages")
    name = models.CharField(max_length=200)
    order = models.PositiveIntegerField()
    category = models.CharField(
        max_length=20, choices=WorkflowStageCategory.choices, default=WorkflowStageCategory.BACKLOG
    )
    progress_percent = models.PositiveSmallIntegerField(default=0)
    is_done = models.BooleanField(default=False)
    is_qa = models.BooleanField(default=False)
    counts_as_wip = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workflow", "order"],
                name="unique_workflow_stage_order",
            ),
            models.UniqueConstraint(
                fields=["workflow"],
                condition=Q(is_done=True),
                name="unique_workflow_done_stage",
            ),
        ]
        indexes = [
            models.Index(fields=["workflow", "order"]),
            models.Index(fields=["workflow", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.workflow_id}, order={self.order})"
