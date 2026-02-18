from __future__ import annotations

import json
import uuid

from django.db import IntegrityError, transaction
from django.db.models import Case, IntegerField, When
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from audit.services import write_audit_event
from identity.models import Org, OrgMembership

from .models import Workflow, WorkflowStage

_STAGE_CATEGORIES = {"backlog", "in_progress", "qa", "done"}


def _json_error(message: str, *, status: int) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def _parse_json(request: HttpRequest) -> dict:
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise ValueError("invalid JSON") from None

    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")

    return payload


def _parse_int(value, field: str) -> int:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be an integer") from None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be an integer") from None
    return parsed


def _parse_progress_percent(value, field: str) -> int:
    parsed = _parse_int(value, field)
    if parsed < 0 or parsed > 100:
        raise ValueError(f"{field} must be between 0 and 100") from None
    return parsed


def _require_stage_category(value, field: str) -> str:
    if value is None:
        raise ValueError(f"{field} is required") from None
    category = str(value).strip()
    if category not in _STAGE_CATEGORIES:
        raise ValueError(f"{field} must be one of: backlog, in_progress, qa, done") from None
    return category


def _require_authenticated_user(request: HttpRequest):
    if not request.user.is_authenticated:
        return None
    return request.user


def _get_api_key_principal(request: HttpRequest):
    return getattr(request, "api_key_principal", None)


def _principal_has_scope(principal, required: str) -> bool:
    scopes = set(getattr(principal, "scopes", None) or [])
    if required == "read":
        return "read" in scopes or "write" in scopes
    return required in scopes


def _require_org(org_id) -> Org | None:
    return Org.objects.filter(id=org_id).first()


def _require_read_access(
    request: HttpRequest, org: Org
) -> tuple[OrgMembership | None, object | None, JsonResponse | None]:
    principal = _get_api_key_principal(request)
    if principal is not None:
        if str(org.id) != str(principal.org_id):
            return None, None, _json_error("forbidden", status=403)
        if not _principal_has_scope(principal, "read"):
            return None, None, _json_error("forbidden", status=403)
        return None, principal, None

    user = _require_authenticated_user(request)
    if user is None:
        return None, None, _json_error("unauthorized", status=401)

    membership = (
        OrgMembership.objects.filter(user=user, org=org)
        .select_related("org")
        .order_by("created_at")
        .first()
    )
    if membership is None:
        return None, None, _json_error("forbidden", status=403)

    return membership, None, None


def _require_write_access(
    request: HttpRequest, org: Org
) -> tuple[OrgMembership | None, object | None, JsonResponse | None]:
    principal = _get_api_key_principal(request)
    if principal is not None:
        if str(org.id) != str(principal.org_id):
            return None, None, _json_error("forbidden", status=403)
        if not _principal_has_scope(principal, "write"):
            return None, None, _json_error("forbidden", status=403)
        return None, principal, None

    user = _require_authenticated_user(request)
    if user is None:
        return None, None, _json_error("unauthorized", status=401)

    membership = OrgMembership.objects.filter(user=user, org=org).select_related("org").first()
    if membership is None:
        return None, None, _json_error("forbidden", status=403)
    if membership.role not in {OrgMembership.Role.ADMIN, OrgMembership.Role.PM}:
        return None, None, _json_error("forbidden", status=403)

    return membership, None, None


def _workflow_dict(workflow: Workflow) -> dict:
    return {
        "id": str(workflow.id),
        "org_id": str(workflow.org_id),
        "name": workflow.name,
        "created_by_user_id": str(workflow.created_by_user_id)
        if workflow.created_by_user_id
        else None,
        "created_at": workflow.created_at.isoformat(),
        "updated_at": workflow.updated_at.isoformat(),
    }


def _stage_dict(stage: WorkflowStage) -> dict:
    return {
        "id": str(stage.id),
        "workflow_id": str(stage.workflow_id),
        "name": stage.name,
        "order": stage.order,
        "category": str(getattr(stage, "category", "") or ""),
        "progress_percent": int(getattr(stage, "progress_percent", 0) or 0),
        "is_done": stage.is_done,
        "is_qa": stage.is_qa,
        "counts_as_wip": stage.counts_as_wip,
        "created_at": stage.created_at.isoformat(),
        "updated_at": stage.updated_at.isoformat(),
    }


def _require_done_stage_count(stages: list[dict], *, exactly_one: bool) -> None:
    done_count = sum(1 for s in stages if bool(s.get("is_done")) is True)
    if exactly_one and done_count != 1:
        raise ValueError("stages must include exactly one is_done=true stage")
    if not exactly_one and done_count == 0:
        raise ValueError("workflow must have a done stage")


def _build_stage_payloads(stages_raw) -> list[dict]:
    if not isinstance(stages_raw, list) or not stages_raw:
        raise ValueError("stages must be a non-empty list")

    stages: list[dict] = []
    for idx, raw in enumerate(stages_raw):
        if not isinstance(raw, dict):
            raise ValueError("stages must be a list of objects")

        name = str(raw.get("name", "")).strip()
        if not name:
            raise ValueError(f"stages[{idx}].name is required")

        order = _parse_int(raw.get("order"), f"stages[{idx}].order")
        if order < 1:
            raise ValueError(f"stages[{idx}].order must be >= 1")

        category = _require_stage_category(raw.get("category"), f"stages[{idx}].category")
        progress_percent = _parse_progress_percent(
            raw.get("progress_percent", 0), f"stages[{idx}].progress_percent"
        )
        is_done = bool(raw.get("is_done", False))
        if category == "done":
            is_done = True
            progress_percent = 100
        elif is_done:
            category = "done"
            progress_percent = 100

        stages.append(
            {
                "name": name,
                "order": order,
                "category": category,
                "progress_percent": progress_percent,
                "is_done": is_done,
                "is_qa": bool(raw.get("is_qa", False)),
                "counts_as_wip": bool(raw.get("counts_as_wip", False)),
            }
        )

    _require_done_stage_count(stages, exactly_one=True)

    orders = [s["order"] for s in stages]
    if len(orders) != len(set(orders)):
        raise ValueError("stage orders must be unique")

    stages.sort(key=lambda s: (s["order"], s["name"]))
    for idx, stage in enumerate(stages, start=1):
        stage["order"] = idx

    return stages


def _stage_ordered_list(workflow: Workflow) -> list[WorkflowStage]:
    return list(workflow.stages.order_by("order", "created_at", "id"))


def _apply_stage_orders(workflow: Workflow, final_order_by_id: dict[uuid.UUID, int]) -> None:
    stages = list(
        WorkflowStage.objects.filter(workflow=workflow).only("id", "order").order_by("id")
    )
    if not stages:
        return

    max_order = max(s.order for s in stages)
    temp_base = max_order + 1000
    temp_by_id = {s.id: temp_base + idx for idx, s in enumerate(stages, start=1)}

    with transaction.atomic():
        WorkflowStage.objects.filter(workflow=workflow).update(
            order=Case(
                *[When(id=stage_id, then=value) for stage_id, value in temp_by_id.items()],
                output_field=IntegerField(),
            )
        )
        WorkflowStage.objects.filter(workflow=workflow).update(
            order=Case(
                *[When(id=stage_id, then=value) for stage_id, value in final_order_by_id.items()],
                output_field=IntegerField(),
            )
        )


def _normalize_stage_orders(workflow: Workflow) -> None:
    stages = _stage_ordered_list(workflow)
    final_order_by_id = {s.id: idx for idx, s in enumerate(stages, start=1)}
    _apply_stage_orders(workflow, final_order_by_id)


def _move_stage_to_order(stage: WorkflowStage, desired_order: int) -> None:
    workflow = stage.workflow
    stages = _stage_ordered_list(workflow)
    stages = [s for s in stages if s.id != stage.id]

    bounded = max(1, min(desired_order, len(stages) + 1))
    stages.insert(bounded - 1, stage)

    final_order_by_id = {s.id: idx for idx, s in enumerate(stages, start=1)}
    _apply_stage_orders(workflow, final_order_by_id)


def _assert_workflow_has_exactly_one_done_stage(workflow: Workflow) -> None:
    done_count = workflow.stages.filter(is_done=True).count()
    if done_count != 1:
        raise ValueError("workflow must have exactly one is_done=true stage")


@require_http_methods(["GET", "POST"])
def workflows_collection_view(request: HttpRequest, org_id) -> JsonResponse:
    """List or create workflows for an org.

    Auth: Session or API key (see `docs/api/scope-map.yaml` operations
    `workflows__workflows_get` and `workflows__workflows_post`).
    Inputs: Path `org_id`; POST JSON `{name, stages}`.
    Returns: `{workflows: [...]}` for GET; `{workflow, stages}` for POST.
    Side effects: POST creates a workflow + stages and writes an audit event.
    """
    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        _, _, err = _require_read_access(request, org)
        if err is not None:
            return err

        workflows = Workflow.objects.filter(org=org).order_by("created_at")
        return JsonResponse({"workflows": [_workflow_dict(w) for w in workflows]})

    membership, principal, err = _require_write_access(request, org)
    if err is not None:
        return err

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    name = str(payload.get("name", "")).strip()
    if not name:
        return _json_error("name is required", status=400)

    try:
        stages = _build_stage_payloads(payload.get("stages"))
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    actor_user = membership.user if membership is not None else None
    principal_id = getattr(principal, "api_key_id", None) if principal is not None else None

    try:
        with transaction.atomic():
            workflow = Workflow.objects.create(org=org, name=name, created_by_user=actor_user)
            stage_models = [
                WorkflowStage(workflow=workflow, **stage_payload) for stage_payload in stages
            ]
            WorkflowStage.objects.bulk_create(stage_models)
            _assert_workflow_has_exactly_one_done_stage(workflow)

            write_audit_event(
                org=org,
                actor_user=actor_user,
                event_type="workflow.created",
                metadata={
                    "workflow_id": str(workflow.id),
                    "name": workflow.name,
                    "actor_type": "api_key" if principal is not None else "user",
                    "actor_id": str(principal_id)
                    if principal_id
                    else str(actor_user.id)
                    if actor_user
                    else None,
                },
            )
    except (IntegrityError, ValueError) as exc:
        return _json_error(str(exc), status=400)

    workflow.refresh_from_db()
    stages_out = list(workflow.stages.order_by("order"))
    return JsonResponse(
        {"workflow": _workflow_dict(workflow), "stages": [_stage_dict(s) for s in stages_out]}
    )


@require_http_methods(["GET", "PATCH", "DELETE"])
def workflow_detail_view(request: HttpRequest, org_id, workflow_id) -> JsonResponse:
    """Get, update, or delete a workflow.

    Auth: Session or API key (see `docs/api/scope-map.yaml` operations `workflows__workflow_get`,
    `workflows__workflow_patch`, and `workflows__workflow_delete`).
    Inputs: Path `org_id`, `workflow_id`; PATCH JSON supports `{name}`.
    Returns: `{workflow, stages}` for GET; `{workflow}` for PATCH; 204 for DELETE.
    Side effects: PATCH/DELETE write audit events; DELETE is blocked when referenced by projects,
    tasks, or subtasks.
    """
    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        _, _, err = _require_read_access(request, org)
        if err is not None:
            return err

        workflow = Workflow.objects.filter(id=workflow_id, org=org).first()
        if workflow is None:
            return _json_error("not found", status=404)
        stages = list(workflow.stages.order_by("order"))
        return JsonResponse(
            {"workflow": _workflow_dict(workflow), "stages": [_stage_dict(s) for s in stages]}
        )

    membership, principal, err = _require_write_access(request, org)
    if err is not None:
        return err

    workflow = Workflow.objects.filter(id=workflow_id, org=org).first()
    if workflow is None:
        return _json_error("not found", status=404)

    actor_user = membership.user if membership is not None else None
    principal_id = getattr(principal, "api_key_id", None) if principal is not None else None

    if request.method == "DELETE":
        from work_items.models import Project, Subtask, Task

        if Project.objects.filter(workflow=workflow).exists():
            return _json_error("workflow is assigned to a project", status=400)
        if Subtask.objects.filter(workflow_stage__workflow=workflow).exists():
            return _json_error("workflow stages are referenced by subtasks", status=400)
        if Task.objects.filter(workflow_stage__workflow=workflow).exists():
            return _json_error("workflow stages are referenced by tasks", status=400)

        workflow.delete()

        write_audit_event(
            org=org,
            actor_user=actor_user,
            event_type="workflow.deleted",
            metadata={
                "workflow_id": str(workflow.id),
                "actor_type": "api_key" if principal is not None else "user",
                "actor_id": str(principal_id)
                if principal_id
                else str(actor_user.id)
                if actor_user
                else None,
            },
        )
        return JsonResponse({}, status=204)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    if "name" in payload:
        workflow.name = str(payload.get("name", "")).strip()
        if not workflow.name:
            return _json_error("name is required", status=400)

    workflow.save()

    write_audit_event(
        org=org,
        actor_user=actor_user,
        event_type="workflow.updated",
        metadata={
            "workflow_id": str(workflow.id),
            "name": workflow.name,
            "actor_type": "api_key" if principal is not None else "user",
            "actor_id": str(principal_id)
            if principal_id
            else str(actor_user.id)
            if actor_user
            else None,
        },
    )

    return JsonResponse({"workflow": _workflow_dict(workflow)})


@require_http_methods(["GET", "POST"])
def workflow_stages_collection_view(request: HttpRequest, org_id, workflow_id) -> JsonResponse:
    """List or create workflow stages for a workflow.

    Auth: Session or API key (see `docs/api/scope-map.yaml` operations
    `workflows__workflow_stages_get` and `workflows__workflow_stages_post`).
    Inputs: Path `org_id`, `workflow_id`; POST JSON fields: name, order, category, progress_percent,
    is_done?, is_qa?, counts_as_wip?.
    Returns: `{stages: [...]}` for GET; `{stage, stages}` for POST.
    Side effects: POST enforces a single done stage, reorders stages, and writes an audit event.
    """
    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        _, _, err = _require_read_access(request, org)
        if err is not None:
            return err

        workflow = Workflow.objects.filter(id=workflow_id, org=org).first()
        if workflow is None:
            return _json_error("not found", status=404)

        return JsonResponse({"stages": [_stage_dict(s) for s in workflow.stages.order_by("order")]})

    membership, principal, err = _require_write_access(request, org)
    if err is not None:
        return err

    workflow = Workflow.objects.filter(id=workflow_id, org=org).first()
    if workflow is None:
        return _json_error("not found", status=404)

    actor_user = membership.user if membership is not None else None
    principal_id = getattr(principal, "api_key_id", None) if principal is not None else None

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    name = str(payload.get("name", "")).strip()
    if not name:
        return _json_error("name is required", status=400)

    try:
        category = _require_stage_category(payload.get("category"), "category")
        progress_percent = _parse_progress_percent(
            payload.get("progress_percent", 0), "progress_percent"
        )
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    try:
        desired_order = _parse_int(payload.get("order"), "order")
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    if desired_order < 1:
        return _json_error("order must be >= 1", status=400)

    is_done = bool(payload.get("is_done", False))
    if category == "done":
        is_done = True
        progress_percent = 100
    elif is_done:
        category = "done"
        progress_percent = 100

    stage = WorkflowStage(
        workflow=workflow,
        name=name,
        order=desired_order,
        category=category,
        progress_percent=progress_percent,
        is_done=is_done,
        is_qa=bool(payload.get("is_qa", False)),
        counts_as_wip=bool(payload.get("counts_as_wip", False)),
    )

    try:
        with transaction.atomic():
            if stage.is_done:
                WorkflowStage.objects.filter(workflow=workflow, is_done=True).update(is_done=False)

            max_order = (
                workflow.stages.order_by("-order").values_list("order", flat=True).first() or 0
            )
            stage.order = max_order + 1000
            stage.save()

            _move_stage_to_order(stage, desired_order)
            stage.refresh_from_db()

            _assert_workflow_has_exactly_one_done_stage(workflow)

            write_audit_event(
                org=org,
                actor_user=actor_user,
                event_type="workflow_stage.created",
                metadata={
                    "workflow_id": str(workflow.id),
                    "stage_id": str(stage.id),
                    "actor_type": "api_key" if principal is not None else "user",
                    "actor_id": str(principal_id)
                    if principal_id
                    else str(actor_user.id)
                    if actor_user
                    else None,
                },
            )
    except (IntegrityError, ValueError) as exc:
        return _json_error(str(exc), status=400)

    stages_out = list(workflow.stages.order_by("order"))
    return JsonResponse(
        {"stage": _stage_dict(stage), "stages": [_stage_dict(s) for s in stages_out]}
    )


@require_http_methods(["GET", "PATCH", "DELETE"])
def workflow_stage_detail_view(request: HttpRequest, org_id, workflow_id, stage_id) -> JsonResponse:
    """Get, update, or delete a workflow stage.

    Auth: Session or API key (see `docs/api/scope-map.yaml` operations
    `workflows__workflow_stage_get`, `workflows__workflow_stage_patch`, and
    `workflows__workflow_stage_delete`).
    Inputs: Path `org_id`, `workflow_id`, `stage_id`; PATCH supports
    `{name?, order?, category?, progress_percent?, is_done?, is_qa?, counts_as_wip?}`.
    Returns: `{stage}` for GET; `{stage, stages}` for PATCH; 204 for DELETE.
    Side effects: PATCH/DELETE may reorder stages, enforce a single done stage, and write audit
    events.
    """
    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        _, _, err = _require_read_access(request, org)
        if err is not None:
            return err

        workflow = Workflow.objects.filter(id=workflow_id, org=org).first()
        if workflow is None:
            return _json_error("not found", status=404)

        stage = WorkflowStage.objects.filter(id=stage_id, workflow=workflow).first()
        if stage is None:
            return _json_error("not found", status=404)

        return JsonResponse({"stage": _stage_dict(stage)})

    membership, principal, err = _require_write_access(request, org)
    if err is not None:
        return err

    workflow = Workflow.objects.filter(id=workflow_id, org=org).first()
    if workflow is None:
        return _json_error("not found", status=404)

    stage = WorkflowStage.objects.filter(id=stage_id, workflow=workflow).first()
    if stage is None:
        return _json_error("not found", status=404)

    prior_category = str(getattr(stage, "category", "") or "")

    actor_user = membership.user if membership is not None else None
    principal_id = getattr(principal, "api_key_id", None) if principal is not None else None

    if request.method == "DELETE":
        from work_items.models import Subtask, Task

        if stage.is_done:
            return _json_error("cannot delete the done stage", status=400)
        if workflow.stages.count() <= 1:
            return _json_error("workflow must have at least one stage", status=400)
        if Subtask.objects.filter(workflow_stage=stage).exists():
            return _json_error("stage is referenced by subtasks", status=400)
        if Task.objects.filter(workflow_stage=stage).exists():
            return _json_error("stage is referenced by tasks", status=400)

        with transaction.atomic():
            stage.delete()
            _normalize_stage_orders(workflow)

        write_audit_event(
            org=org,
            actor_user=actor_user,
            event_type="workflow_stage.deleted",
            metadata={
                "workflow_id": str(workflow.id),
                "stage_id": str(stage.id),
                "actor_type": "api_key" if principal is not None else "user",
                "actor_id": str(principal_id)
                if principal_id
                else str(actor_user.id)
                if actor_user
                else None,
            },
        )
        return JsonResponse({}, status=204)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    if not payload:
        return _json_error("no fields to update", status=400)

    desired_order = None
    if "order" in payload:
        try:
            desired_order = _parse_int(payload.get("order"), "order")
        except ValueError as exc:
            return _json_error(str(exc), status=400)
        if desired_order < 1:
            return _json_error("order must be >= 1", status=400)

    if "name" in payload:
        stage.name = str(payload.get("name", "")).strip()
        if not stage.name:
            return _json_error("name is required", status=400)

    category_promotes_to_done = False
    if "category" in payload:
        try:
            category = _require_stage_category(payload.get("category"), "category")
        except ValueError as exc:
            return _json_error(str(exc), status=400)
        if stage.is_done and category != "done":
            return _json_error("done stage must have category=done", status=400)
        stage.category = category
        if category == "done":
            stage.progress_percent = 100
            if not stage.is_done:
                category_promotes_to_done = True

    if "progress_percent" in payload:
        try:
            stage.progress_percent = _parse_progress_percent(
                payload.get("progress_percent"), "progress_percent"
            )
        except ValueError as exc:
            return _json_error(str(exc), status=400)
        if str(getattr(stage, "category", "")) == "done":
            stage.progress_percent = 100

    if "is_qa" in payload:
        stage.is_qa = bool(payload.get("is_qa"))
    if "counts_as_wip" in payload:
        stage.counts_as_wip = bool(payload.get("counts_as_wip"))

    promote_to_done = False
    if "is_done" in payload:
        is_done = bool(payload.get("is_done"))
        if not is_done and stage.is_done:
            return _json_error("workflow must have exactly one done stage", status=400)
        if is_done and not stage.is_done:
            promote_to_done = True
        if is_done:
            stage.category = "done"
            stage.progress_percent = 100
    promote_to_done = promote_to_done or category_promotes_to_done

    try:
        with transaction.atomic():
            stage.save()

            if desired_order is not None:
                _move_stage_to_order(stage, desired_order)
                stage.refresh_from_db()

            if promote_to_done:
                WorkflowStage.objects.filter(workflow=workflow, is_done=True).update(is_done=False)
                stage.is_done = True
                stage.save(update_fields=["is_done", "updated_at"])

            if str(getattr(stage, "category", "") or "") != prior_category:
                from work_items.models import Subtask, Task

                Task.objects.filter(workflow_stage=stage).update(status=stage.category)
                Subtask.objects.filter(workflow_stage=stage).update(status=stage.category)

            _assert_workflow_has_exactly_one_done_stage(workflow)

            write_audit_event(
                org=org,
                actor_user=actor_user,
                event_type="workflow_stage.updated",
                metadata={
                    "workflow_id": str(workflow.id),
                    "stage_id": str(stage.id),
                    "actor_type": "api_key" if principal is not None else "user",
                    "actor_id": str(principal_id)
                    if principal_id
                    else str(actor_user.id)
                    if actor_user
                    else None,
                },
            )
    except (IntegrityError, ValueError) as exc:
        return _json_error(str(exc), status=400)

    stage.refresh_from_db()
    stages_out = list(workflow.stages.order_by("order"))
    return JsonResponse(
        {"stage": _stage_dict(stage), "stages": [_stage_dict(s) for s in stages_out]}
    )
