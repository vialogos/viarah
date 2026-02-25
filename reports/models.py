from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


def report_pdf_upload_to(instance: "ReportRun", filename: str) -> str:
    del filename
    return f"report_pdfs/{instance.org_id}/{instance.id}.pdf"


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
    pdf_file = models.FileField(
        upload_to=report_pdf_upload_to,
        null=True,
        blank=True,
        max_length=500,
    )
    pdf_content_type = models.CharField(max_length=100, blank=True)
    pdf_size_bytes = models.PositiveBigIntegerField(default=0)
    pdf_sha256 = models.CharField(max_length=64, blank=True)
    pdf_rendered_at = models.DateTimeField(null=True, blank=True)
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


class ReportRunPdfRenderLog(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report_run = models.ForeignKey(
        ReportRun,
        on_delete=models.CASCADE,
        related_name="pdf_render_logs",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    celery_task_id = models.CharField(max_length=100, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    blocked_urls = models.JSONField(default=list, blank=True)
    missing_images = models.JSONField(default=list, blank=True)
    error_code = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)
    qa_report = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["report_run", "created_at"]),
            models.Index(fields=["report_run", "status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"ReportRunPdfRenderLog {self.id} ({self.status})"
