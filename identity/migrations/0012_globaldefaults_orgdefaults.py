import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workflows", "0002_workflowstage_category_and_progress_percent"),
        ("identity", "0011_org_logo_file"),
    ]

    operations = [
        migrations.CreateModel(
            name="GlobalDefaults",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True,
                        default=uuid.uuid4,
                        editable=False,
                        serialize=False,
                    ),
                ),
                ("key", models.CharField(default="default", max_length=50, unique=True)),
                (
                    "project_progress_policy",
                    models.CharField(
                        choices=[
                            ("subtasks_rollup", "Subtasks rollup"),
                            ("workflow_stage", "Workflow stage"),
                        ],
                        default="subtasks_rollup",
                        max_length=30,
                    ),
                ),
                (
                    "workflow_stage_template",
                    models.JSONField(
                        blank=True,
                        default=[
                            {
                                "name": "Backlog",
                                "category": "backlog",
                                "progress_percent": 0,
                                "is_qa": False,
                                "counts_as_wip": False,
                            },
                            {
                                "name": "In Progress",
                                "category": "in_progress",
                                "progress_percent": 33,
                                "is_qa": False,
                                "counts_as_wip": True,
                            },
                            {
                                "name": "QA",
                                "category": "qa",
                                "progress_percent": 67,
                                "is_qa": True,
                                "counts_as_wip": True,
                            },
                            {
                                "name": "Done",
                                "category": "done",
                                "progress_percent": 100,
                                "is_qa": False,
                                "counts_as_wip": False,
                            },
                        ],
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["key", "updated_at"], name="identity_glo_key_7dbfdb_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="OrgDefaults",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True,
                        default=uuid.uuid4,
                        editable=False,
                        serialize=False,
                    ),
                ),
                (
                    "project_progress_policy",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("subtasks_rollup", "Subtasks rollup"),
                            ("workflow_stage", "Workflow stage"),
                        ],
                        max_length=30,
                        null=True,
                    ),
                ),
                ("workflow_stage_template", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "default_project_workflow",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="workflows.workflow",
                    ),
                ),
                (
                    "org",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="defaults",
                        to="identity.org",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["org", "updated_at"], name="identity_org_org_0f6d03_idx"),
                ],
            },
        ),
    ]
