from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class SavedView(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey("identity.Org", on_delete=models.CASCADE, related_name="saved_views")
    project = models.ForeignKey(
        "work_items.Project", on_delete=models.CASCADE, related_name="saved_views"
    )
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_views"
    )
    name = models.CharField(max_length=200)
    client_safe = models.BooleanField(default=False)
    filters = models.JSONField(default=dict, blank=True)
    sort = models.JSONField(default=dict, blank=True)
    group_by = models.CharField(max_length=50, default="none")
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["org", "project", "owner_user", "created_at"]),
            models.Index(fields=["org", "project", "owner_user", "archived_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["owner_user", "project", "name"], name="unique_saved_view_name_per_owner"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.project_id})"


class CustomFieldDefinition(models.Model):
    class FieldType(models.TextChoices):
        TEXT = "text", "Text"
        NUMBER = "number", "Number"
        DATE = "date", "Date"
        SELECT = "select", "Select"
        MULTI_SELECT = "multi_select", "Multi-select"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        "identity.Org", on_delete=models.CASCADE, related_name="custom_field_definitions"
    )
    project = models.ForeignKey(
        "work_items.Project", on_delete=models.CASCADE, related_name="custom_field_definitions"
    )
    name = models.CharField(max_length=200)
    field_type = models.CharField(max_length=20, choices=FieldType.choices)
    options = models.JSONField(default=list, blank=True)
    client_safe = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["project", "created_at"]),
            models.Index(fields=["project", "archived_at"]),
            models.Index(fields=["org", "project", "client_safe"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"], name="unique_custom_field_name_per_project"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.project_id})"


class CustomFieldValue(models.Model):
    class WorkItemType(models.TextChoices):
        TASK = "task", "Task"
        SUBTASK = "subtask", "Subtask"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        "identity.Org", on_delete=models.CASCADE, related_name="custom_field_values"
    )
    project = models.ForeignKey(
        "work_items.Project", on_delete=models.CASCADE, related_name="custom_field_values"
    )
    field = models.ForeignKey(
        CustomFieldDefinition, on_delete=models.CASCADE, related_name="values"
    )
    work_item_type = models.CharField(max_length=10, choices=WorkItemType.choices)
    work_item_id = models.UUIDField()
    value_json = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["project", "work_item_type", "work_item_id"]),
            models.Index(fields=["field", "work_item_type", "work_item_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["field", "work_item_type", "work_item_id"],
                name="unique_custom_field_value_per_work_item",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.field_id} {self.work_item_type} {self.work_item_id}"
