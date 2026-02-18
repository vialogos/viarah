from __future__ import annotations

import uuid

from django.db import migrations, models


def _find_stage_candidates(stages: list[object]) -> dict[str, uuid.UUID | None]:
    if not stages:
        return {
            "backlog": None,
            "in_progress": None,
            "qa": None,
            "done": None,
            "fallback_highest": None,
        }

    ordered = sorted(
        stages,
        key=lambda s: (
            int(getattr(s, "order", 0)),
            str(getattr(s, "name", "")).lower(),
            str(getattr(s, "id", "")),
        ),
    )

    backlog_stage = next((s for s in ordered if int(s.order) == 1), None)
    done_stage = next((s for s in ordered if bool(getattr(s, "is_done", False)) is True), None)

    qa_stage = next((s for s in ordered if bool(getattr(s, "is_qa", False)) is True), None)
    if qa_stage is None:
        qa_stage = next((s for s in ordered if str(getattr(s, "name", "")).strip().lower() == "qa"), None)

    wip_stage = next((s for s in ordered if bool(getattr(s, "counts_as_wip", False)) is True), None)
    if wip_stage is None:
        wip_stage = next(
            (
                s
                for s in ordered
                if int(s.order) > 1
                and (done_stage is None or s.id != done_stage.id)
                and (qa_stage is None or s.id != qa_stage.id)
            ),
            None,
        )

    fallback_highest = ordered[-1]

    return {
        "backlog": getattr(backlog_stage, "id", None),
        "in_progress": getattr(wip_stage, "id", None) or getattr(backlog_stage, "id", None),
        "qa": getattr(qa_stage, "id", None)
        or getattr(wip_stage, "id", None)
        or getattr(backlog_stage, "id", None),
        "done": getattr(done_stage, "id", None) or getattr(fallback_highest, "id", None),
        "fallback_highest": getattr(fallback_highest, "id", None),
    }


def forwards(apps, schema_editor) -> None:
    Task = apps.get_model("work_items", "Task")
    Subtask = apps.get_model("work_items", "Subtask")
    WorkflowStage = apps.get_model("workflows", "WorkflowStage")

    stages_by_workflow_id: dict[str, list[object]] = {}
    for stage in WorkflowStage.objects.all().only(
        "id", "workflow_id", "order", "name", "is_done", "is_qa", "counts_as_wip", "category"
    ):
        stages_by_workflow_id.setdefault(str(stage.workflow_id), []).append(stage)

    candidates_by_workflow_id: dict[str, dict[str, uuid.UUID | None]] = {}
    for workflow_id, stages in stages_by_workflow_id.items():
        candidates_by_workflow_id[workflow_id] = _find_stage_candidates(stages)

    # First, align existing subtasks already staged.
    subtasks_to_update: list[object] = []
    for subtask in (
        Subtask.objects.filter(workflow_stage_id__isnull=False)
        .select_related("workflow_stage")
        .only("id", "status", "workflow_stage_id", "workflow_stage__category")
    ):
        category = getattr(subtask.workflow_stage, "category", None)
        if category and str(subtask.status) != str(category):
            subtask.status = category
            subtasks_to_update.append(subtask)
    if subtasks_to_update:
        Subtask.objects.bulk_update(subtasks_to_update, ["status"])

    # Then, backfill task workflow_stage from legacy status (idempotent; do not overwrite).
    tasks_to_update: list[object] = []
    task_qs = (
        Task.objects.filter(workflow_stage_id__isnull=True)
        .select_related("epic", "epic__project")
        .only("id", "status", "workflow_stage_id", "epic__project__workflow_id")
    )
    for task in task_qs.iterator():
        workflow_id = getattr(task.epic.project, "workflow_id", None)
        if workflow_id is None:
            continue

        candidates = candidates_by_workflow_id.get(str(workflow_id))
        if not candidates:
            continue

        status = str(getattr(task, "status", "") or "").strip()
        if not status:
            continue

        stage_id = candidates.get(status)
        if stage_id is None:
            continue

        task.workflow_stage_id = stage_id
        tasks_to_update.append(task)

    if tasks_to_update:
        Task.objects.bulk_update(tasks_to_update, ["workflow_stage_id"])

    # Finally, align legacy status for any tasks that now have (or already had) a workflow stage.
    staged_tasks_to_update: list[object] = []
    for task in (
        Task.objects.filter(workflow_stage_id__isnull=False)
        .select_related("workflow_stage")
        .only("id", "status", "workflow_stage_id", "workflow_stage__category")
    ):
        category = getattr(task.workflow_stage, "category", None)
        if category and str(task.status) != str(category):
            task.status = category
            staged_tasks_to_update.append(task)
    if staged_tasks_to_update:
        Task.objects.bulk_update(staged_tasks_to_update, ["status"])


def backwards(apps, schema_editor) -> None:
    # Leave data in place; schema rollback is handled by Django.
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("workflows", "0002_workflowstage_category_and_progress_percent"),
        ("work_items", "0005_task_assignee_user"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="progress_policy",
            field=models.CharField(
                choices=[
                    ("subtasks_rollup", "Subtasks rollup"),
                    ("workflow_stage", "Workflow stage"),
                    ("manual", "Manual"),
                ],
                default="subtasks_rollup",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="epic",
            name="progress_policy",
            field=models.CharField(
                blank=True,
                choices=[
                    ("subtasks_rollup", "Subtasks rollup"),
                    ("workflow_stage", "Workflow stage"),
                    ("manual", "Manual"),
                ],
                max_length=30,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="epic",
            name="manual_progress_percent",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="task",
            name="workflow_stage",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="tasks",
                to="workflows.workflowstage",
            ),
        ),
        migrations.AddField(
            model_name="task",
            name="progress_policy",
            field=models.CharField(
                blank=True,
                choices=[
                    ("subtasks_rollup", "Subtasks rollup"),
                    ("workflow_stage", "Workflow stage"),
                    ("manual", "Manual"),
                ],
                max_length=30,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="task",
            name="manual_progress_percent",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(forwards, backwards),
    ]
