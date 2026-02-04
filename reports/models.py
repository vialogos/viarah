from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class ReportRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey("identity.Org", on_delete=models.CASCADE, related_name="report_runs")
    project = models.ForeignKey(
        "work_items.Project", on_delete=models.CASCADE, related_name="report_runs"
    )
    template = models.ForeignKey(
        "templates.Template", on_delete=models.PROTECT, related_name="report_runs"
    )
    template_version = models.ForeignKey(
        "templates.TemplateVersion", on_delete=models.PROTECT, related_name="report_runs"
    )
    scope = models.JSONField(default=dict, blank=True)
    output_markdown = models.TextField(blank=True)
    output_html = models.TextField(blank=True)
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_report_runs",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["org", "created_at"]),
            models.Index(fields=["org", "project", "created_at"]),
            models.Index(fields=["template", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"ReportRun ({self.project_id})"

