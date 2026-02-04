from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class TemplateType(models.TextChoices):
    REPORT = "report", "Report"
    EMAIL = "email", "Email"
    COMMENT = "comment", "Comment"
    SOW = "sow", "SoW"


class Template(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey("identity.Org", on_delete=models.CASCADE, related_name="templates")
    type = models.CharField(max_length=20, choices=TemplateType.choices)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    current_version = models.ForeignKey(
        "templates.TemplateVersion",
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
        related_name="created_templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org", "type", "name"], name="template_unique_name_per_org_type"
            )
        ]
        indexes = [
            models.Index(fields=["org", "created_at"]),
            models.Index(fields=["org", "type", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.org_id})"

    def clean(self):
        self.name = self.name.strip()


class TemplateVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(Template, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    body = models.TextField()
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_template_versions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["template", "version"], name="template_version_unique_per_template"
            )
        ]
        indexes = [
            models.Index(fields=["template", "created_at"]),
            models.Index(fields=["template", "version"]),
        ]

    def __str__(self) -> str:
        return f"v{self.version} ({self.template_id})"
