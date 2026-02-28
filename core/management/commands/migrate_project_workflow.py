from __future__ import annotations

import json
import uuid
from collections.abc import Iterable

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from work_items.models import Project, Subtask, Task
from workflows.models import Workflow, WorkflowStage


def _uuid_arg(value: str, *, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        raise CommandError(f"{name} must be a UUID") from None


def _unique(values: Iterable[uuid.UUID | None]) -> list[uuid.UUID]:
    return sorted({v for v in values if v is not None})


class Command(BaseCommand):
    help = "Reassign a project's workflow safely (migrate or clear workflow_stage_id)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--project-id", required=True, help="Project UUID.")
        parser.add_argument("--workflow-id", required=True, help="Target workflow UUID (same org).")
        parser.add_argument(
            "--strategy",
            choices=["order", "clear"],
            default="order",
            help="Migration strategy: map stages by order (default) or clear all stages.",
        )
        parser.add_argument(
            "--clear-unmapped",
            action="store_true",
            help="When --strategy=order, clear stages with no matching order instead of failing.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the plan but do not modify the database.",
        )

    def handle(self, *args, **options) -> str | None:
        project_id = _uuid_arg(options["project_id"], name="--project-id")
        workflow_id = _uuid_arg(options["workflow_id"], name="--workflow-id")
        strategy = str(options["strategy"] or "order")
        clear_unmapped = bool(options["clear_unmapped"])
        dry_run = bool(options["dry_run"])

        project = Project.objects.filter(id=project_id).select_related("org", "workflow").first()
        if project is None:
            raise CommandError("project not found")

        target_workflow = (
            Workflow.objects.filter(id=workflow_id, org=project.org)
            .prefetch_related("stages")
            .first()
        )
        if target_workflow is None:
            raise CommandError("target workflow not found (must be in the same org)")

        tasks_qs = Task.objects.filter(epic__project=project).only(
            "id", "workflow_stage_id", "status"
        )
        subtasks_qs = Subtask.objects.filter(task__epic__project=project).only(
            "id", "workflow_stage_id", "status"
        )

        staged_task_stage_ids = _unique(tasks_qs.values_list("workflow_stage_id", flat=True))
        staged_subtask_stage_ids = _unique(subtasks_qs.values_list("workflow_stage_id", flat=True))
        staged_stage_ids = sorted(set(staged_task_stage_ids) | set(staged_subtask_stage_ids))

        if strategy == "clear":
            plan = {
                "project_id": str(project.id),
                "org_id": str(project.org_id),
                "prior_workflow_id": str(project.workflow_id) if project.workflow_id else None,
                "workflow_id": str(target_workflow.id),
                "strategy": strategy,
                "dry_run": dry_run,
                "tasks": {
                    "count": tasks_qs.count(),
                    "staged_count": tasks_qs.filter(workflow_stage_id__isnull=False).count(),
                    "cleared_count": tasks_qs.filter(workflow_stage_id__isnull=False).count(),
                },
                "subtasks": {
                    "count": subtasks_qs.count(),
                    "staged_count": subtasks_qs.filter(workflow_stage_id__isnull=False).count(),
                    "cleared_count": subtasks_qs.filter(workflow_stage_id__isnull=False).count(),
                },
            }

            if not dry_run:
                with transaction.atomic():
                    tasks_qs.update(workflow_stage_id=None)
                    subtasks_qs.update(workflow_stage_id=None)
                    project.workflow = target_workflow
                    project.save(update_fields=["workflow", "updated_at"])

            return json.dumps(plan)

        if strategy != "order":
            raise CommandError("invalid strategy")

        if not staged_stage_ids:
            plan = {
                "project_id": str(project.id),
                "org_id": str(project.org_id),
                "prior_workflow_id": str(project.workflow_id) if project.workflow_id else None,
                "workflow_id": str(target_workflow.id),
                "strategy": strategy,
                "dry_run": dry_run,
                "note": (
                    "no staged tasks/subtasks; workflow can be reassigned without stage migration"
                ),
                "mappings": [],
            }
            if not dry_run:
                project.workflow = target_workflow
                project.save(update_fields=["workflow", "updated_at"])
            return json.dumps(plan)

        if project.workflow_id is None:
            raise CommandError(
                "project has no workflow assigned but has staged tasks/subtasks; "
                "use --strategy=clear"
            )

        source_workflow_id = project.workflow_id
        staged_stages = list(
            WorkflowStage.objects.filter(id__in=staged_stage_ids).only(
                "id", "workflow_id", "order", "category"
            )
        )
        stage_by_id = {s.id: s for s in staged_stages}

        for stage_id in staged_stage_ids:
            stage = stage_by_id.get(stage_id)
            if stage is None:
                raise CommandError("staged workflow_stage_id not found")
            if stage.workflow_id != source_workflow_id:
                raise CommandError(
                    "found staged workflow_stage_id that does not belong to the project's "
                    "current workflow; use --strategy=clear"
                )

        target_by_order = {s.order: s for s in list(getattr(target_workflow, "stages").all())}
        mappings: list[dict[str, str | int | None]] = []
        updates: list[tuple[uuid.UUID, uuid.UUID | None, str | None]] = []

        for stage in staged_stages:
            target_stage = target_by_order.get(stage.order)
            if target_stage is None:
                if not clear_unmapped:
                    raise CommandError(
                        f"target workflow is missing stage order={stage.order}; re-run with "
                        "--clear-unmapped or --strategy=clear"
                    )
                updates.append((stage.id, None, None))
                mappings.append(
                    {
                        "source_stage_id": str(stage.id),
                        "source_order": stage.order,
                        "target_stage_id": None,
                        "target_order": stage.order,
                    }
                )
                continue

            updates.append((stage.id, target_stage.id, str(target_stage.category)))
            mappings.append(
                {
                    "source_stage_id": str(stage.id),
                    "source_order": stage.order,
                    "target_stage_id": str(target_stage.id),
                    "target_order": target_stage.order,
                }
            )

        if not dry_run:
            with transaction.atomic():
                for source_stage_id, target_stage_id, target_category in updates:
                    if target_stage_id is None:
                        Task.objects.filter(
                            epic__project=project, workflow_stage_id=source_stage_id
                        ).update(workflow_stage_id=None)
                        Subtask.objects.filter(
                            task__epic__project=project, workflow_stage_id=source_stage_id
                        ).update(workflow_stage_id=None)
                        continue

                    Task.objects.filter(
                        epic__project=project, workflow_stage_id=source_stage_id
                    ).update(
                        workflow_stage_id=target_stage_id,
                        status=str(target_category or ""),
                    )
                    Subtask.objects.filter(
                        task__epic__project=project, workflow_stage_id=source_stage_id
                    ).update(
                        workflow_stage_id=target_stage_id,
                        status=str(target_category or ""),
                    )

                project.workflow = target_workflow
                project.save(update_fields=["workflow", "updated_at"])

        plan = {
            "project_id": str(project.id),
            "org_id": str(project.org_id),
            "prior_workflow_id": str(source_workflow_id),
            "workflow_id": str(target_workflow.id),
            "strategy": strategy,
            "clear_unmapped": clear_unmapped,
            "dry_run": dry_run,
            "mappings": mappings,
        }
        return json.dumps(plan)
