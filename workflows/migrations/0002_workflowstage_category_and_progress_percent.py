from __future__ import annotations

from django.db import migrations, models


def _infer_category(stage) -> str:
    if bool(stage.is_done) is True:
        return "done"
    if bool(stage.is_qa) is True:
        return "qa"
    if bool(stage.counts_as_wip) is True:
        return "in_progress"
    if int(stage.order) == 1:
        return "backlog"
    return "in_progress"


def forwards(apps, schema_editor) -> None:
    WorkflowStage = apps.get_model("workflows", "WorkflowStage")

    stages_by_workflow_id: dict[str, list] = {}
    for stage in WorkflowStage.objects.all().order_by("workflow_id", "order", "id"):
        stages_by_workflow_id.setdefault(str(stage.workflow_id), []).append(stage)

    for stages in stages_by_workflow_id.values():
        done_order = None
        for stage in stages:
            if bool(stage.is_done) is True:
                done_order = int(stage.order)
                break

        for stage in stages:
            category = _infer_category(stage)
            if category == "done":
                progress_percent = 100
            elif category == "backlog":
                progress_percent = 0
            else:
                if done_order is not None and done_order > 1:
                    raw = (float(stage.order) - 1.0) / (float(done_order) - 1.0)
                    progress_percent = int(round(raw * 100.0))
                else:
                    progress_percent = 0
                progress_percent = max(0, min(progress_percent, 100))

            stage.category = category
            stage.progress_percent = progress_percent

        WorkflowStage.objects.bulk_update(stages, ["category", "progress_percent"])


def backwards(apps, schema_editor) -> None:
    WorkflowStage = apps.get_model("workflows", "WorkflowStage")
    WorkflowStage.objects.update(category="backlog", progress_percent=0)


class Migration(migrations.Migration):
    dependencies = [
        ("workflows", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowstage",
            name="category",
            field=models.CharField(
                choices=[
                    ("backlog", "Backlog"),
                    ("in_progress", "In progress"),
                    ("qa", "QA"),
                    ("done", "Done"),
                ],
                default="backlog",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="workflowstage",
            name="progress_percent",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.RunPython(forwards, backwards),
    ]

