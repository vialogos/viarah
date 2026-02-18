from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class WorkItemStatus(models.TextChoices):
    BACKLOG = "backlog", "Backlog"
    IN_PROGRESS = "in_progress", "In progress"
    QA = "qa", "QA"
    DONE = "done", "Done"


class ProgressPolicy(models.TextChoices):
    SUBTASKS_ROLLUP = "subtasks_rollup", "Subtasks rollup"
    WORKFLOW_STAGE = "workflow_stage", "Workflow stage"
    MANUAL = "manual", "Manual"


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey("identity.Org", on_delete=models.CASCADE, related_name="projects")
    workflow = models.ForeignKey(
        "workflows.Workflow",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="projects",
    )
    progress_policy = models.CharField(
        max_length=30,
        choices=ProgressPolicy.choices,
        default=ProgressPolicy.SUBTASKS_ROLLUP,
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["org", "created_at"]),
            models.Index(fields=["org", "workflow"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.org_id})"


class Epic(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="epics")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=WorkItemStatus.choices, null=True, blank=True)
    progress_policy = models.CharField(
        max_length=30, choices=ProgressPolicy.choices, null=True, blank=True
    )
    manual_progress_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["project", "created_at"]),
            models.Index(fields=["project", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.project_id})"


class Task(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    epic = models.ForeignKey(Epic, on_delete=models.CASCADE, related_name="tasks")
    workflow_stage = models.ForeignKey(
        "workflows.WorkflowStage",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="tasks",
    )
    assignee_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_tasks",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=WorkItemStatus.choices, default=WorkItemStatus.BACKLOG
    )
    progress_policy = models.CharField(
        max_length=30, choices=ProgressPolicy.choices, null=True, blank=True
    )
    manual_progress_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    client_safe = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(start_date__isnull=True)
                    | models.Q(end_date__isnull=True)
                    | models.Q(start_date__lte=models.F("end_date"))
                ),
                name="task_start_date_lte_end_date",
            )
        ]
        indexes = [
            models.Index(fields=["epic", "created_at"]),
            models.Index(fields=["epic", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.epic_id})"


class Subtask(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="subtasks")
    workflow_stage = models.ForeignKey(
        "workflows.WorkflowStage",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="subtasks",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=WorkItemStatus.choices, default=WorkItemStatus.BACKLOG
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(start_date__isnull=True)
                    | models.Q(end_date__isnull=True)
                    | models.Q(start_date__lte=models.F("end_date"))
                ),
                name="subtask_start_date_lte_end_date",
            )
        ]
        indexes = [
            models.Index(fields=["task", "created_at"]),
            models.Index(fields=["task", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.task_id})"
