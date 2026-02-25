from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


def sow_pdf_upload_to(instance: "SoWPdfArtifact", filename: str) -> str:
    del filename
    sow_version_id = str(getattr(instance, "sow_version_id", "") or "unknown")
    org_id = "unknown"
    try:
        org_id = str(instance.sow_version.sow.org_id)
    except Exception:  # noqa: BLE001
        org_id = "unknown"
    return f"sow_pdfs/{org_id}/{sow_version_id}.pdf"


class SoW(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey("identity.Org", on_delete=models.CASCADE, related_name="sows")
    project = models.ForeignKey("work_items.Project", on_delete=models.CASCADE, related_name="sows")
    template = models.ForeignKey(
        "templates.Template", on_delete=models.PROTECT, related_name="sows"
    )
    current_version = models.ForeignKey(
        "sows.SoWVersion",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_sows",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["org", "created_at"]),
            models.Index(fields=["org", "project", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"SoW ({self.project_id})"


class SoWVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_SIGNATURE = "pending_signature", "Pending signature"
        SIGNED = "signed", "Signed"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sow = models.ForeignKey(SoW, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    template_version = models.ForeignKey(
        "templates.TemplateVersion",
        on_delete=models.PROTECT,
        related_name="sow_versions",
    )
    variables_json = models.JSONField(default=dict, blank=True)
    body_markdown = models.TextField(blank=True)
    body_html = models.TextField(blank=True)
    content_sha256 = models.CharField(max_length=64, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_sow_versions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["sow", "version"], name="sow_version_unique_per_sow"),
        ]
        indexes = [
            models.Index(fields=["sow", "created_at"]),
            models.Index(fields=["sow", "status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"SoWVersion v{self.version} ({self.sow_id})"


class SoWSigner(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sow_version = models.ForeignKey(SoWVersion, on_delete=models.CASCADE, related_name="signers")
    signer_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sow_signers"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    decision_comment = models.TextField(blank=True)
    typed_signature = models.CharField(max_length=200, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sow_version", "signer_user"], name="sow_signer_unique_per_version_user"
            ),
        ]
        indexes = [
            models.Index(fields=["sow_version", "status", "created_at"]),
            models.Index(fields=["signer_user", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"SoWSigner {self.signer_user_id} ({self.sow_version_id})"


class SoWPdfArtifact(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sow_version = models.OneToOneField(
        SoWVersion,
        on_delete=models.CASCADE,
        related_name="pdf_artifact",
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
    pdf_file = models.FileField(
        upload_to=sow_pdf_upload_to,
        null=True,
        blank=True,
        max_length=500,
    )
    pdf_content_type = models.CharField(max_length=100, blank=True)
    pdf_size_bytes = models.PositiveBigIntegerField(default=0)
    pdf_sha256 = models.CharField(max_length=64, blank=True)
    pdf_rendered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["sow_version", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"SoWPdfArtifact {self.id} ({self.status})"
