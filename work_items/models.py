from __future__ import annotations

import uuid

from django.db import models


class WorkItemStatus(models.TextChoices):
    BACKLOG = "backlog", "Backlog"
    IN_PROGRESS = "in_progress", "In progress"
    QA = "qa", "QA"
    DONE = "done", "Done"


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey("identity.Org", on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["org", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.org_id})"


class Epic(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="epics")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=WorkItemStatus.choices, null=True, blank=True)
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
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=WorkItemStatus.choices, default=WorkItemStatus.BACKLOG
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["epic", "created_at"]),
            models.Index(fields=["epic", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.epic_id})"


class Subtask(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="subtasks")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=WorkItemStatus.choices, default=WorkItemStatus.BACKLOG
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["task", "created_at"]),
            models.Index(fields=["task", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.task_id})"
