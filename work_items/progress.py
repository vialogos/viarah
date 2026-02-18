from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Iterable

from workflows.models import WorkflowStage


@dataclass(frozen=True, slots=True)
class WorkflowProgressContext:
    workflow_id: uuid.UUID
    stage_count: int
    done_stage_id: uuid.UUID | None
    done_stage_order: int | None
    stage_order_by_id: dict[uuid.UUID, int]
    stage_is_done_by_id: dict[uuid.UUID, bool]
    stage_category_by_id: dict[uuid.UUID, str]
    stage_progress_percent_by_id: dict[uuid.UUID, int]


def build_workflow_progress_context(
    *, workflow_id: uuid.UUID, stages: Iterable[WorkflowStage]
) -> tuple[WorkflowProgressContext, str | None]:
    """
    Build a stable in-memory view of workflow stage ordering and the "done" stage.

    We return a context object even when the workflow is misconfigured so callers can still
    provide a consistent `progress_why` payload (stage counts, detected done order, etc.)
    without raising/500ing.
    """

    stage_order_by_id: dict[uuid.UUID, int] = {}
    stage_is_done_by_id: dict[uuid.UUID, bool] = {}
    stage_category_by_id: dict[uuid.UUID, str] = {}
    stage_progress_percent_by_id: dict[uuid.UUID, int] = {}
    done_stages: list[WorkflowStage] = []
    stage_count = 0

    for stage in stages:
        stage_count += 1
        stage_order_by_id[stage.id] = int(stage.order)
        stage_is_done_by_id[stage.id] = bool(stage.is_done)
        stage_category_by_id[stage.id] = str(getattr(stage, "category", "") or "")
        stage_progress_percent_by_id[stage.id] = int(getattr(stage, "progress_percent", 0) or 0)
        if stage.is_done:
            done_stages.append(stage)

    done_stage_id: uuid.UUID | None = None
    done_stage_order: int | None = None
    reason: str | None = None

    if stage_count == 0:
        reason = "workflow_has_no_stages"
    elif len(done_stages) == 0:
        reason = "workflow_missing_done_stage"
    elif len(done_stages) > 1:
        reason = "workflow_multiple_done_stages"
    else:
        done_stage_id = done_stages[0].id
        done_stage_order = int(done_stages[0].order)
        if done_stage_order <= 1:
            reason = "workflow_done_stage_at_start"

    return (
        WorkflowProgressContext(
            workflow_id=workflow_id,
            stage_count=stage_count,
            done_stage_id=done_stage_id,
            done_stage_order=done_stage_order,
            stage_order_by_id=stage_order_by_id,
            stage_is_done_by_id=stage_is_done_by_id,
            stage_category_by_id=stage_category_by_id,
            stage_progress_percent_by_id=stage_progress_percent_by_id,
        ),
        reason,
    )


def compute_subtask_progress(
    *,
    project_workflow_id: uuid.UUID | None,
    workflow_ctx: WorkflowProgressContext | None,
    workflow_ctx_reason: str | None,
    workflow_stage_id: uuid.UUID | None,
) -> tuple[float, dict]:
    """
    Compute subtask progress deterministically from workflow stage ordering.

    Policy (v2):
    - Uses explicit per-stage `progress_percent` (0..100) from the project workflow stage.
    - If workflow is misconfigured, return 0.0 with a clear `progress_why.reason`.
    """

    why: dict = {
        "policy": "stage_progress_percent",
        "workflow_id": str(project_workflow_id) if project_workflow_id else None,
        "workflow_stage_id": str(workflow_stage_id) if workflow_stage_id else None,
    }

    if project_workflow_id is None:
        why["reason"] = "project_missing_workflow"
        return 0.0, why

    if workflow_ctx is None:
        why["reason"] = "workflow_context_unavailable"
        return 0.0, why

    why["stage_count"] = workflow_ctx.stage_count
    why["done_stage_order"] = workflow_ctx.done_stage_order

    if workflow_ctx_reason is not None:
        why["reason"] = workflow_ctx_reason
        return 0.0, why

    if workflow_stage_id is None:
        why["reason"] = "subtask_missing_workflow_stage"
        return 0.0, why

    stage_order = workflow_ctx.stage_order_by_id.get(workflow_stage_id)
    why["stage_order"] = stage_order
    if stage_order is None:
        why["reason"] = "stage_not_in_project_workflow"
        return 0.0, why

    percent = workflow_ctx.stage_progress_percent_by_id.get(workflow_stage_id)
    why["progress_percent"] = percent
    if percent is None:
        why["reason"] = "stage_progress_unavailable"
        return 0.0, why

    clamped = max(0, min(int(percent), 100))
    if clamped != int(percent):
        why["reason"] = "stage_progress_percent_clamped"
    return float(clamped) / 100.0, why


def compute_rollup_progress(
    *,
    project_workflow_id: uuid.UUID | None,
    workflow_ctx: WorkflowProgressContext | None,
    workflow_ctx_reason: str | None,
    workflow_stage_ids: Iterable[uuid.UUID | None],
) -> tuple[float, dict]:
    """
    Compute task/epic progress as a count-based average of subtask progress values.

    This preserves the "single source of truth" for subtask progress while providing a
    deterministic rollup for parents.
    """

    stage_ids = list(workflow_stage_ids)
    subtask_count = len(stage_ids)

    why: dict = {
        "policy": "average_of_subtask_progress",
        "workflow_id": str(project_workflow_id) if project_workflow_id else None,
        "subtask_count": subtask_count,
    }

    if subtask_count == 0:
        why["reason"] = "no_subtasks"
        return 0.0, why

    if project_workflow_id is None:
        why["reason"] = "project_missing_workflow"
        return 0.0, why

    if workflow_ctx is None:
        why["reason"] = "workflow_context_unavailable"
        return 0.0, why

    why["stage_count"] = workflow_ctx.stage_count
    why["done_stage_order"] = workflow_ctx.done_stage_order

    if workflow_ctx_reason is not None:
        why["reason"] = workflow_ctx_reason
        return 0.0, why

    counts_by_stage_order: dict[str, int] = {}
    missing_stage_count = 0
    unknown_stage_count = 0
    missing_progress_count = 0
    clamped_progress_count = 0
    progress_sum = 0.0

    for stage_id in stage_ids:
        if stage_id is None:
            missing_stage_count += 1
            counts_by_stage_order["unassigned"] = counts_by_stage_order.get("unassigned", 0) + 1
            continue

        stage_order = workflow_ctx.stage_order_by_id.get(stage_id)
        if stage_order is None:
            unknown_stage_count += 1
            counts_by_stage_order["unknown"] = counts_by_stage_order.get("unknown", 0) + 1
            continue

        counts_by_stage_order[str(stage_order)] = counts_by_stage_order.get(str(stage_order), 0) + 1

        percent = workflow_ctx.stage_progress_percent_by_id.get(stage_id)
        if percent is None:
            missing_progress_count += 1
            continue

        clamped = max(0, min(int(percent), 100))
        if clamped != int(percent):
            clamped_progress_count += 1
        progress_sum += float(clamped) / 100.0

    why["subtask_progress_sum"] = progress_sum
    why["subtask_counts_by_stage_order"] = counts_by_stage_order
    why["subtasks_missing_stage_count"] = missing_stage_count
    why["subtasks_unknown_stage_count"] = unknown_stage_count
    why["subtasks_missing_progress_count"] = missing_progress_count
    why["subtasks_clamped_progress_count"] = clamped_progress_count

    return progress_sum / float(subtask_count), why
