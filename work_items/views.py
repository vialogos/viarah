from __future__ import annotations

import datetime
import json
import re
import uuid

from django.db.models import Prefetch
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from audit.services import write_audit_event
from customization.models import CustomFieldDefinition, CustomFieldValue
from identity.models import Org, OrgMembership
from notifications.models import NotificationEventType
from notifications.services import emit_assignment_changed, emit_project_event
from realtime.services import publish_org_event
from workflows.models import Workflow, WorkflowStage

from .models import Epic, Project, Subtask, Task, WorkItemStatus
from .progress import (
    WorkflowProgressContext,
    build_workflow_progress_context,
    compute_rollup_progress,
    compute_subtask_progress,
)

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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


def _principal_project_id(principal) -> uuid.UUID | None:
    project_id = getattr(principal, "project_id", None)
    if project_id is None or str(project_id).strip() == "":
        return None
    try:
        return uuid.UUID(str(project_id))
    except (TypeError, ValueError):
        return None


def _require_work_items_membership(user, org_id) -> OrgMembership | None:
    membership = (
        OrgMembership.objects.filter(user=user, org_id=org_id).select_related("org").first()
    )
    if membership is None:
        return None
    if membership.role not in {
        OrgMembership.Role.ADMIN,
        OrgMembership.Role.PM,
        OrgMembership.Role.MEMBER,
    }:
        return None
    return membership


def _require_work_items_read_membership(user, org_id) -> OrgMembership | None:
    membership = (
        OrgMembership.objects.filter(user=user, org_id=org_id).select_related("org").first()
    )
    if membership is None:
        return None
    if membership.role not in {
        OrgMembership.Role.ADMIN,
        OrgMembership.Role.PM,
        OrgMembership.Role.MEMBER,
        OrgMembership.Role.CLIENT,
    }:
        return None
    return membership


def _require_org(org_id) -> Org | None:
    return Org.objects.filter(id=org_id).first()


def _require_org_access(
    request: HttpRequest, org_id, *, required_scope: str, allow_client: bool
) -> tuple[Org | None, OrgMembership | None, object | None, JsonResponse | None]:
    org = _require_org(org_id)
    if org is None:
        return None, None, None, _json_error("not found", status=404)

    principal = _get_api_key_principal(request)
    if principal is not None:
        if str(org.id) != str(principal.org_id):
            return org, None, principal, _json_error("forbidden", status=403)
        if not _principal_has_scope(principal, required_scope):
            return org, None, principal, _json_error("forbidden", status=403)
        return org, None, principal, None

    user = _require_authenticated_user(request)
    if user is None:
        return org, None, None, _json_error("unauthorized", status=401)

    if allow_client:
        membership = _require_work_items_read_membership(user, org.id)
    else:
        membership = _require_work_items_membership(user, org.id)

    if membership is None:
        return org, None, None, _json_error("forbidden", status=403)

    return org, membership, None, None


def _require_status_param(status_raw: str | None) -> str | None:
    if status_raw is None or not str(status_raw).strip():
        return None

    status = str(status_raw).strip()
    if status not in set(WorkItemStatus.values):
        raise ValueError("invalid status")
    return status


def _workflow_progress_context_for_project(
    project: Project,
) -> tuple[WorkflowProgressContext | None, str | None]:
    if project.workflow_id is None:
        return None, "project_missing_workflow"

    stages = list(
        WorkflowStage.objects.filter(workflow_id=project.workflow_id)
        .only("id", "order", "is_done")
        .order_by("order", "created_at", "id")
    )
    ctx, reason = build_workflow_progress_context(workflow_id=project.workflow_id, stages=stages)
    return ctx, reason


def _custom_field_values_by_work_item_ids(
    *,
    project_id: uuid.UUID,
    work_item_type: str,
    work_item_ids: list[uuid.UUID],
    client_safe_only: bool,
) -> dict[uuid.UUID, list[dict]]:
    if not work_item_ids:
        return {}

    field_defs = CustomFieldDefinition.objects.filter(
        project_id=project_id, archived_at__isnull=True
    )
    if client_safe_only:
        field_defs = field_defs.filter(client_safe=True)

    field_ids = list(field_defs.values_list("id", flat=True))
    if not field_ids:
        return {}

    rows = (
        CustomFieldValue.objects.filter(
            project_id=project_id,
            work_item_type=work_item_type,
            work_item_id__in=work_item_ids,
            field_id__in=field_ids,
        )
        .values("work_item_id", "field_id", "value_json")
        .order_by("field_id")
    )
    mapping: dict[uuid.UUID, list[dict]] = {}
    for row in rows:
        work_item_id = row["work_item_id"]
        mapping.setdefault(work_item_id, []).append(
            {"field_id": str(row["field_id"]), "value": row["value_json"]}
        )
    return mapping


def _project_dict(project: Project) -> dict:
    return {
        "id": str(project.id),
        "org_id": str(project.org_id),
        "workflow_id": str(project.workflow_id) if project.workflow_id else None,
        "name": project.name,
        "description": project.description,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }


def _project_client_safe_dict(project: Project) -> dict:
    return {
        "id": str(project.id),
        "org_id": str(project.org_id),
        "name": project.name,
        "updated_at": project.updated_at.isoformat(),
    }


def _epic_dict(epic: Epic) -> dict:
    return {
        "id": str(epic.id),
        "project_id": str(epic.project_id),
        "title": epic.title,
        "description": epic.description,
        "status": epic.status,
        "created_at": epic.created_at.isoformat(),
        "updated_at": epic.updated_at.isoformat(),
    }


def _task_dict(task: Task) -> dict:
    return {
        "id": str(task.id),
        "epic_id": str(task.epic_id),
        "assignee_user_id": str(task.assignee_user_id) if task.assignee_user_id else None,
        "title": task.title,
        "description": task.description,
        "start_date": task.start_date.isoformat() if task.start_date else None,
        "end_date": task.end_date.isoformat() if task.end_date else None,
        "status": task.status,
        "client_safe": bool(task.client_safe),
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def _subtask_dict(subtask: Subtask) -> dict:
    return {
        "id": str(subtask.id),
        "task_id": str(subtask.task_id),
        "workflow_stage_id": str(subtask.workflow_stage_id) if subtask.workflow_stage_id else None,
        "title": subtask.title,
        "description": subtask.description,
        "start_date": subtask.start_date.isoformat() if subtask.start_date else None,
        "end_date": subtask.end_date.isoformat() if subtask.end_date else None,
        "status": subtask.status,
        "created_at": subtask.created_at.isoformat(),
        "updated_at": subtask.updated_at.isoformat(),
    }


def _task_client_safe_dict(task: Task) -> dict:
    return {
        "id": str(task.id),
        "epic_id": str(task.epic_id),
        "title": task.title,
        "status": task.status,
        "start_date": task.start_date.isoformat() if task.start_date else None,
        "end_date": task.end_date.isoformat() if task.end_date else None,
        "updated_at": task.updated_at.isoformat(),
    }


def _subtask_client_safe_dict(subtask: Subtask) -> dict:
    return {
        "id": str(subtask.id),
        "task_id": str(subtask.task_id),
        "workflow_stage_id": str(subtask.workflow_stage_id) if subtask.workflow_stage_id else None,
        "title": subtask.title,
        "status": subtask.status,
        "start_date": subtask.start_date.isoformat() if subtask.start_date else None,
        "end_date": subtask.end_date.isoformat() if subtask.end_date else None,
    }


def _parse_date_value(value, field: str) -> datetime.date | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string in YYYY-MM-DD format or null") from None

    value_str = value.strip()
    if not value_str or not _ISO_DATE_RE.fullmatch(value_str):
        raise ValueError(f"{field} must be YYYY-MM-DD") from None

    try:
        return datetime.date.fromisoformat(value_str)
    except ValueError:
        raise ValueError(f"{field} must be a valid date") from None


def _parse_nullable_date_field(payload: dict, field: str) -> tuple[bool, datetime.date | None]:
    if field not in payload:
        return False, None
    return True, _parse_date_value(payload.get(field), field)


@require_http_methods(["GET", "POST"])
def projects_collection_view(request: HttpRequest, org_id) -> JsonResponse:
    required_scope = "read" if request.method == "GET" else "write"
    org, membership, principal, err = _require_org_access(
        request, org_id, required_scope=required_scope, allow_client=request.method == "GET"
    )
    if err is not None:
        return err

    if request.method == "GET":
        projects = Project.objects.filter(org=org)
        if principal is not None:
            project_id_restriction = _principal_project_id(principal)
            if project_id_restriction is not None:
                projects = projects.filter(id=project_id_restriction)
        projects = projects.order_by("created_at")
        client_safe_only = membership is not None and membership.role == OrgMembership.Role.CLIENT
        if client_safe_only:
            return JsonResponse({"projects": [_project_client_safe_dict(p) for p in projects]})
        return JsonResponse({"projects": [_project_dict(p) for p in projects]})

    if principal is not None and _principal_project_id(principal) is not None:
        return _json_error("forbidden", status=403)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    name = str(payload.get("name", "")).strip()
    description = str(payload.get("description", "")).strip()
    if not name:
        return _json_error("name is required", status=400)

    project = Project.objects.create(org=org, name=name, description=description)
    return JsonResponse({"project": _project_dict(project)})


@require_http_methods(["GET", "PATCH", "DELETE"])
def project_detail_view(request: HttpRequest, org_id, project_id) -> JsonResponse:
    required_scope = "read" if request.method == "GET" else "write"
    org, membership, principal, err = _require_org_access(
        request, org_id, required_scope=required_scope, allow_client=request.method == "GET"
    )
    if err is not None:
        return err

    project_qs = Project.objects.filter(id=project_id, org=org)
    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None:
            project_qs = project_qs.filter(id=project_id_restriction)

    project = project_qs.first()
    if project is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        client_safe_only = membership is not None and membership.role == OrgMembership.Role.CLIENT
        if client_safe_only:
            return JsonResponse({"project": _project_client_safe_dict(project)})
        return JsonResponse({"project": _project_dict(project)})

    if request.method == "DELETE":
        project.delete()
        return JsonResponse({}, status=204)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    fields_to_update: list[str] = []
    workflow_changed = False
    prior_workflow_id = str(project.workflow_id) if project.workflow_id else None
    desired_workflow_id = prior_workflow_id

    if "workflow_id" in payload:
        if membership is not None and membership.role not in {
            OrgMembership.Role.ADMIN,
            OrgMembership.Role.PM,
        }:
            return _json_error("forbidden", status=403)

        workflow_id_raw = payload.get("workflow_id")
        if workflow_id_raw is None:
            new_workflow = None
        else:
            try:
                workflow_uuid = uuid.UUID(str(workflow_id_raw))
            except (TypeError, ValueError):
                return _json_error("workflow_id must be a UUID or null", status=400)

            new_workflow = Workflow.objects.filter(id=workflow_uuid, org=org).first()
            if new_workflow is None:
                return _json_error("invalid workflow_id", status=400)

        desired_workflow_id = str(new_workflow.id) if new_workflow else None
        workflow_changed = desired_workflow_id != prior_workflow_id

        if workflow_changed:
            has_staged_subtasks = Subtask.objects.filter(
                task__epic__project=project, workflow_stage__isnull=False
            ).exists()
            if has_staged_subtasks:
                return _json_error(
                    "cannot change workflow while subtasks have workflow_stage_id set", status=400
                )

            project.workflow = new_workflow
            fields_to_update.append("workflow")

    if "name" in payload:
        project.name = str(payload.get("name", "")).strip()
        if not project.name:
            return _json_error("name is required", status=400)
        fields_to_update.append("name")

    if "description" in payload:
        project.description = str(payload.get("description", "")).strip()
        fields_to_update.append("description")

    if fields_to_update:
        unique_update_fields = list(dict.fromkeys(fields_to_update))
        project.save(update_fields=[*unique_update_fields, "updated_at"])

    if workflow_changed:
        actor_user = membership.user if membership is not None else None
        principal_id = getattr(principal, "api_key_id", None) if principal is not None else None
        write_audit_event(
            org=org,
            actor_user=actor_user,
            event_type="project.workflow_assigned",
            metadata={
                "project_id": str(project.id),
                "prior_workflow_id": prior_workflow_id,
                "workflow_id": desired_workflow_id,
                "actor_type": "api_key" if principal is not None else "user",
                "actor_id": str(principal_id)
                if principal_id
                else str(actor_user.id)
                if actor_user
                else None,
            },
        )
    return JsonResponse({"project": _project_dict(project)})


@require_http_methods(["GET", "POST"])
def project_epics_collection_view(request: HttpRequest, org_id, project_id) -> JsonResponse:
    required_scope = "read" if request.method == "GET" else "write"
    org, _, principal, err = _require_org_access(
        request, org_id, required_scope=required_scope, allow_client=False
    )
    if err is not None:
        return err

    project_qs = Project.objects.filter(id=project_id, org=org)
    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None:
            project_qs = project_qs.filter(id=project_id_restriction)

    project = project_qs.first()
    if project is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        workflow_ctx, workflow_ctx_reason = _workflow_progress_context_for_project(project)
        task_prefetch = Prefetch(
            "tasks",
            queryset=Task.objects.only("id", "epic_id").prefetch_related(
                Prefetch(
                    "subtasks",
                    queryset=Subtask.objects.only("id", "task_id", "workflow_stage_id"),
                )
            ),
        )
        epics = (
            Epic.objects.filter(project=project)
            .prefetch_related(task_prefetch)
            .order_by("created_at")
        )

        epic_payloads: list[dict] = []
        for epic in epics:
            stage_ids: list[uuid.UUID | None] = []
            task_count = 0
            for task in epic.tasks.all():
                task_count += 1
                stage_ids.extend([s.workflow_stage_id for s in task.subtasks.all()])

            progress, why = compute_rollup_progress(
                project_workflow_id=project.workflow_id,
                workflow_ctx=workflow_ctx,
                workflow_ctx_reason=workflow_ctx_reason,
                workflow_stage_ids=stage_ids,
            )
            why["task_count"] = task_count

            payload = _epic_dict(epic)
            payload["progress"] = progress
            payload["progress_why"] = why
            epic_payloads.append(payload)

        return JsonResponse({"epics": epic_payloads})

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    if "start_date" in payload or "end_date" in payload:
        return _json_error("scheduling fields are not supported for epics", status=400)

    title = str(payload.get("title", "")).strip()
    description = str(payload.get("description", "")).strip()
    status_raw = payload.get("status")
    if not title:
        return _json_error("title is required", status=400)

    if status_raw is not None:
        try:
            status = _require_status_param(status_raw)
        except ValueError:
            return _json_error("invalid status", status=400)
    else:
        status = None

    epic = Epic.objects.create(project=project, title=title, description=description, status=status)
    progress, why = compute_rollup_progress(
        project_workflow_id=project.workflow_id,
        workflow_ctx=None,
        workflow_ctx_reason=None,
        workflow_stage_ids=[],
    )
    why["task_count"] = 0
    payload = _epic_dict(epic)
    payload["progress"] = progress
    payload["progress_why"] = why
    return JsonResponse({"epic": payload})


@require_http_methods(["GET", "PATCH", "DELETE"])
def epic_detail_view(request: HttpRequest, org_id, epic_id) -> JsonResponse:
    required_scope = "read" if request.method == "GET" else "write"
    org, membership, principal, err = _require_org_access(
        request, org_id, required_scope=required_scope, allow_client=False
    )
    if err is not None:
        return err

    task_prefetch = Prefetch(
        "tasks",
        queryset=Task.objects.only("id", "epic_id").prefetch_related(
            Prefetch(
                "subtasks",
                queryset=Subtask.objects.only("id", "task_id", "workflow_stage_id"),
            )
        ),
    )
    epic_qs = (
        Epic.objects.filter(id=epic_id, project__org_id=org.id)
        .select_related("project")
        .prefetch_related(task_prefetch)
    )
    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None:
            epic_qs = epic_qs.filter(project_id=project_id_restriction)

    epic = epic_qs.first()
    if epic is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        workflow_ctx, workflow_ctx_reason = _workflow_progress_context_for_project(epic.project)
        stage_ids: list[uuid.UUID | None] = []
        task_count = 0
        for task in epic.tasks.all():
            task_count += 1
            stage_ids.extend([s.workflow_stage_id for s in task.subtasks.all()])
        progress, why = compute_rollup_progress(
            project_workflow_id=epic.project.workflow_id,
            workflow_ctx=workflow_ctx,
            workflow_ctx_reason=workflow_ctx_reason,
            workflow_stage_ids=stage_ids,
        )
        why["task_count"] = task_count

        payload = _epic_dict(epic)
        payload["progress"] = progress
        payload["progress_why"] = why
        return JsonResponse({"epic": payload})

    if request.method == "DELETE":
        epic.delete()
        return JsonResponse({}, status=204)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    if "start_date" in payload or "end_date" in payload:
        return _json_error("scheduling fields are not supported for epics", status=400)

    if "title" in payload:
        epic.title = str(payload.get("title", "")).strip()
        if not epic.title:
            return _json_error("title is required", status=400)

    if "description" in payload:
        epic.description = str(payload.get("description", "")).strip()

    if "status" in payload:
        status_raw = payload.get("status")
        if status_raw is None or str(status_raw).strip() == "":
            epic.status = None
        else:
            try:
                epic.status = _require_status_param(status_raw)
            except ValueError:
                return _json_error("invalid status", status=400)

    epic.save()
    workflow_ctx, workflow_ctx_reason = _workflow_progress_context_for_project(epic.project)
    stage_ids = []
    task_count = 0
    for task in epic.tasks.all():
        task_count += 1
        stage_ids.extend([s.workflow_stage_id for s in task.subtasks.all()])
    progress, why = compute_rollup_progress(
        project_workflow_id=epic.project.workflow_id,
        workflow_ctx=workflow_ctx,
        workflow_ctx_reason=workflow_ctx_reason,
        workflow_stage_ids=stage_ids,
    )
    why["task_count"] = task_count

    payload = _epic_dict(epic)
    payload["progress"] = progress
    payload["progress_why"] = why
    return JsonResponse({"epic": payload})


@require_http_methods(["POST"])
def epic_tasks_collection_view(request: HttpRequest, org_id, epic_id) -> JsonResponse:
    org, _, principal, err = _require_org_access(
        request, org_id, required_scope="write", allow_client=False
    )
    if err is not None:
        return err

    epic_qs = Epic.objects.filter(id=epic_id, project__org_id=org.id).select_related("project")
    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None:
            epic_qs = epic_qs.filter(project_id=project_id_restriction)

    epic = epic_qs.first()
    if epic is None:
        return _json_error("not found", status=404)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    title = str(payload.get("title", "")).strip()
    description = str(payload.get("description", "")).strip()
    status_raw = payload.get("status")
    if not title:
        return _json_error("title is required", status=400)

    try:
        start_date = (
            _parse_date_value(payload.get("start_date"), "start_date")
            if "start_date" in payload
            else None
        )
        end_date = (
            _parse_date_value(payload.get("end_date"), "end_date")
            if "end_date" in payload
            else None
        )
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    if start_date is not None and end_date is not None and start_date > end_date:
        return _json_error("start_date must be <= end_date", status=400)

    if status_raw is not None:
        try:
            status = _require_status_param(status_raw) or WorkItemStatus.BACKLOG
        except ValueError:
            return _json_error("invalid status", status=400)
    else:
        status = WorkItemStatus.BACKLOG

    task = Task.objects.create(
        epic=epic,
        title=title,
        description=description,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )
    progress, why = compute_rollup_progress(
        project_workflow_id=epic.project.workflow_id,
        workflow_ctx=None,
        workflow_ctx_reason=None,
        workflow_stage_ids=[],
    )
    payload = _task_dict(task)
    payload["custom_field_values"] = []
    payload["progress"] = progress
    payload["progress_why"] = why
    return JsonResponse({"task": payload})


@require_http_methods(["GET"])
def project_tasks_list_view(request: HttpRequest, org_id, project_id) -> JsonResponse:
    org, membership, principal, err = _require_org_access(
        request, org_id, required_scope="read", allow_client=True
    )
    if err is not None:
        return err

    project_qs = Project.objects.filter(id=project_id, org_id=org.id)
    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None:
            project_qs = project_qs.filter(id=project_id_restriction)

    project = project_qs.first()
    if project is None:
        return _json_error("not found", status=404)

    workflow_ctx, workflow_ctx_reason = _workflow_progress_context_for_project(project)

    status_raw = request.GET.get("status")
    try:
        status = _require_status_param(status_raw)
    except ValueError:
        return _json_error("invalid status", status=400)

    tasks = Task.objects.filter(epic__project_id=project.id, epic__project__org_id=org.id)
    client_safe_only = membership is not None and membership.role == OrgMembership.Role.CLIENT
    if client_safe_only:
        tasks = tasks.filter(client_safe=True)
    if status is not None:
        tasks = tasks.filter(status=status)
    tasks = tasks.select_related("epic", "epic__project").prefetch_related(
        Prefetch(
            "subtasks",
            queryset=Subtask.objects.only("id", "task_id", "workflow_stage_id"),
        )
    )
    tasks = tasks.order_by("created_at")
    task_list = list(tasks)
    last_updated_at = max((t.updated_at for t in task_list), default=None)
    custom_values_by_task_id = _custom_field_values_by_work_item_ids(
        project_id=project.id,
        work_item_type=CustomFieldValue.WorkItemType.TASK,
        work_item_ids=[t.id for t in task_list],
        client_safe_only=client_safe_only,
    )

    if client_safe_only:
        payloads: list[dict] = []
        for task in task_list:
            stage_ids = [s.workflow_stage_id for s in task.subtasks.all()]
            progress, why = compute_rollup_progress(
                project_workflow_id=project.workflow_id,
                workflow_ctx=workflow_ctx,
                workflow_ctx_reason=workflow_ctx_reason,
                workflow_stage_ids=stage_ids,
            )
            payload = _task_client_safe_dict(task)
            payload["custom_field_values"] = custom_values_by_task_id.get(task.id, [])
            payload["progress"] = progress
            payload["progress_why"] = why
            payloads.append(payload)
        return JsonResponse(
            {
                "last_updated_at": last_updated_at.isoformat() if last_updated_at else None,
                "tasks": payloads,
            }
        )

    payloads = []
    for task in task_list:
        stage_ids = [s.workflow_stage_id for s in task.subtasks.all()]
        progress, why = compute_rollup_progress(
            project_workflow_id=project.workflow_id,
            workflow_ctx=workflow_ctx,
            workflow_ctx_reason=workflow_ctx_reason,
            workflow_stage_ids=stage_ids,
        )
        payload = _task_dict(task)
        payload["custom_field_values"] = custom_values_by_task_id.get(task.id, [])
        payload["progress"] = progress
        payload["progress_why"] = why
        payloads.append(payload)
    return JsonResponse(
        {
            "last_updated_at": last_updated_at.isoformat() if last_updated_at else None,
            "tasks": payloads,
        }
    )


@require_http_methods(["GET", "PATCH", "DELETE"])
def task_detail_view(request: HttpRequest, org_id, task_id) -> JsonResponse:
    required_scope = "read" if request.method == "GET" else "write"
    org, membership, principal, err = _require_org_access(
        request, org_id, required_scope=required_scope, allow_client=True
    )
    if err is not None:
        return err

    task_qs = (
        Task.objects.filter(id=task_id, epic__project__org_id=org.id)
        .select_related("epic", "epic__project")
        .prefetch_related(
            Prefetch(
                "subtasks",
                queryset=Subtask.objects.only("id", "task_id", "workflow_stage_id"),
            )
        )
    )
    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None:
            task_qs = task_qs.filter(epic__project_id=project_id_restriction)

    task = task_qs.first()
    if task is None:
        return _json_error("not found", status=404)

    project = task.epic.project
    prior_status = str(task.status or "")
    prior_assignee_user_id = str(task.assignee_user_id) if task.assignee_user_id else None

    workflow_ctx, workflow_ctx_reason = _workflow_progress_context_for_project(project)
    stage_ids = [s.workflow_stage_id for s in task.subtasks.all()]
    task_progress, task_progress_why = compute_rollup_progress(
        project_workflow_id=project.workflow_id,
        workflow_ctx=workflow_ctx,
        workflow_ctx_reason=workflow_ctx_reason,
        workflow_stage_ids=stage_ids,
    )

    if request.method == "GET":
        client_safe_only = membership is not None and membership.role == OrgMembership.Role.CLIENT
        if client_safe_only and not task.client_safe:
            return _json_error("not found", status=404)
        if client_safe_only:
            payload = _task_client_safe_dict(task)
        else:
            payload = _task_dict(task)

        custom_values_by_task_id = _custom_field_values_by_work_item_ids(
            project_id=task.epic.project_id,
            work_item_type=CustomFieldValue.WorkItemType.TASK,
            work_item_ids=[task.id],
            client_safe_only=client_safe_only,
        )
        payload["custom_field_values"] = custom_values_by_task_id.get(task.id, [])
        payload["progress"] = task_progress
        payload["progress_why"] = task_progress_why
        return JsonResponse({"task": payload})

    if membership is not None and membership.role == OrgMembership.Role.CLIENT:
        return _json_error("forbidden", status=403)

    if request.method == "DELETE":
        task.delete()
        return JsonResponse({}, status=204)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    try:
        start_present, start_date = _parse_nullable_date_field(payload, "start_date")
        end_present, end_date = _parse_nullable_date_field(payload, "end_date")
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    if start_present or end_present:
        new_start = start_date if start_present else task.start_date
        new_end = end_date if end_present else task.end_date
        if new_start is not None and new_end is not None and new_start > new_end:
            return _json_error("start_date must be <= end_date", status=400)

    if "title" in payload:
        task.title = str(payload.get("title", "")).strip()
        if not task.title:
            return _json_error("title is required", status=400)

    if "description" in payload:
        task.description = str(payload.get("description", "")).strip()

    if "status" in payload:
        try:
            task.status = _require_status_param(payload.get("status")) or task.status
        except ValueError:
            return _json_error("invalid status", status=400)

    if "assignee_user_id" in payload:
        raw_assignee_user_id = payload.get("assignee_user_id")
        if raw_assignee_user_id is None:
            task.assignee_user_id = None
        else:
            try:
                assignee_uuid = uuid.UUID(str(raw_assignee_user_id))
            except (TypeError, ValueError):
                return _json_error("assignee_user_id must be a UUID or null", status=400)

            assignee_membership = OrgMembership.objects.filter(
                org=org, user_id=assignee_uuid
            ).first()
            if assignee_membership is None:
                return _json_error("assignee_user_id must be an org member", status=400)

            task.assignee_user_id = assignee_uuid

    if "client_safe" in payload:
        if membership is not None and membership.role not in {
            OrgMembership.Role.ADMIN,
            OrgMembership.Role.PM,
        }:
            return _json_error("forbidden", status=403)
        task.client_safe = bool(payload.get("client_safe", False))

    if start_present:
        task.start_date = start_date
    if end_present:
        task.end_date = end_date

    task.save()

    actor_user = membership.user if membership is not None else None
    if "assignee_user_id" in payload:
        next_assignee_user_id = str(task.assignee_user_id) if task.assignee_user_id else None
        if prior_assignee_user_id != next_assignee_user_id and next_assignee_user_id is not None:
            emit_assignment_changed(
                org=org,
                project=project,
                actor_user=actor_user,
                task_id=str(task.id),
                old_assignee_user_id=prior_assignee_user_id,
                new_assignee_user_id=next_assignee_user_id,
            )

    if "status" in payload:
        next_status = str(task.status or "")
        if prior_status != next_status:
            emit_project_event(
                org=org,
                project=project,
                event_type=NotificationEventType.STATUS_CHANGED,
                actor_user=actor_user,
                data={
                    "work_item_type": "task",
                    "work_item_id": str(task.id),
                    "old_status": prior_status,
                    "new_status": next_status,
                },
                client_visible=bool(task.client_safe),
            )

    payload = _task_dict(task)
    custom_values_by_task_id = _custom_field_values_by_work_item_ids(
        project_id=task.epic.project_id,
        work_item_type=CustomFieldValue.WorkItemType.TASK,
        work_item_ids=[task.id],
        client_safe_only=False,
    )
    payload["custom_field_values"] = custom_values_by_task_id.get(task.id, [])
    payload["progress"] = task_progress
    payload["progress_why"] = task_progress_why
    return JsonResponse({"task": payload})


@require_http_methods(["GET", "POST"])
def task_subtasks_collection_view(request: HttpRequest, org_id, task_id) -> JsonResponse:
    required_scope = "read" if request.method == "GET" else "write"
    org, membership, principal, err = _require_org_access(
        request, org_id, required_scope=required_scope, allow_client=True
    )
    if err is not None:
        return err

    task_qs = Task.objects.filter(id=task_id, epic__project__org_id=org.id).select_related(
        "epic", "epic__project"
    )
    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None:
            task_qs = task_qs.filter(epic__project_id=project_id_restriction)

    task = task_qs.first()
    if task is None:
        return _json_error("not found", status=404)

    if membership is not None and membership.role == OrgMembership.Role.CLIENT:
        return _json_error("forbidden", status=403)

    project = task.epic.project
    workflow_ctx, workflow_ctx_reason = _workflow_progress_context_for_project(project)

    status_raw = request.GET.get("status")
    try:
        status = _require_status_param(status_raw)
    except ValueError:
        return _json_error("invalid status", status=400)

    if request.method == "GET":
        subtasks = Subtask.objects.filter(task=task)
        if status is not None:
            subtasks = subtasks.filter(status=status)
        subtasks = list(subtasks.order_by("created_at"))
        client_safe_only = membership is not None and membership.role == OrgMembership.Role.CLIENT
        custom_values_by_subtask_id = _custom_field_values_by_work_item_ids(
            project_id=project.id,
            work_item_type=CustomFieldValue.WorkItemType.SUBTASK,
            work_item_ids=[s.id for s in subtasks],
            client_safe_only=client_safe_only,
        )
        if client_safe_only:
            payloads: list[dict] = []
            for subtask in subtasks:
                progress, why = compute_subtask_progress(
                    project_workflow_id=project.workflow_id,
                    workflow_ctx=workflow_ctx,
                    workflow_ctx_reason=workflow_ctx_reason,
                    workflow_stage_id=subtask.workflow_stage_id,
                )
                payload = _subtask_client_safe_dict(subtask)
                payload["custom_field_values"] = custom_values_by_subtask_id.get(subtask.id, [])
                payload["progress"] = progress
                payload["progress_why"] = why
                payloads.append(payload)
            return JsonResponse({"subtasks": payloads})

        payloads = []
        for subtask in subtasks:
            progress, why = compute_subtask_progress(
                project_workflow_id=project.workflow_id,
                workflow_ctx=workflow_ctx,
                workflow_ctx_reason=workflow_ctx_reason,
                workflow_stage_id=subtask.workflow_stage_id,
            )
            payload = _subtask_dict(subtask)
            payload["custom_field_values"] = custom_values_by_subtask_id.get(subtask.id, [])
            payload["progress"] = progress
            payload["progress_why"] = why
            payloads.append(payload)
        return JsonResponse({"subtasks": payloads})

    if membership is not None and membership.role == OrgMembership.Role.CLIENT:
        return _json_error("forbidden", status=403)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    title = str(payload.get("title", "")).strip()
    description = str(payload.get("description", "")).strip()
    status_raw = payload.get("status")
    if not title:
        return _json_error("title is required", status=400)

    try:
        start_date = (
            _parse_date_value(payload.get("start_date"), "start_date")
            if "start_date" in payload
            else None
        )
        end_date = (
            _parse_date_value(payload.get("end_date"), "end_date")
            if "end_date" in payload
            else None
        )
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    if start_date is not None and end_date is not None and start_date > end_date:
        return _json_error("start_date must be <= end_date", status=400)

    if status_raw is not None:
        try:
            status = _require_status_param(status_raw) or WorkItemStatus.BACKLOG
        except ValueError:
            return _json_error("invalid status", status=400)
    else:
        status = WorkItemStatus.BACKLOG

    subtask = Subtask.objects.create(
        task=task,
        title=title,
        description=description,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )
    progress, why = compute_subtask_progress(
        project_workflow_id=project.workflow_id,
        workflow_ctx=workflow_ctx,
        workflow_ctx_reason=workflow_ctx_reason,
        workflow_stage_id=subtask.workflow_stage_id,
    )
    payload = _subtask_dict(subtask)
    payload["custom_field_values"] = []
    payload["progress"] = progress
    payload["progress_why"] = why
    return JsonResponse({"subtask": payload})


@require_http_methods(["GET", "PATCH", "DELETE"])
def subtask_detail_view(request: HttpRequest, org_id, subtask_id) -> JsonResponse:
    required_scope = "read" if request.method == "GET" else "write"
    org, membership, principal, err = _require_org_access(
        request, org_id, required_scope=required_scope, allow_client=True
    )
    if err is not None:
        return err

    subtask_qs = Subtask.objects.filter(
        id=subtask_id, task__epic__project__org_id=org.id
    ).select_related("task", "task__epic", "task__epic__project", "task__epic__project__workflow")
    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None:
            subtask_qs = subtask_qs.filter(task__epic__project_id=project_id_restriction)

    subtask = subtask_qs.first()
    if subtask is None:
        return _json_error("not found", status=404)

    prior_status = str(subtask.status or "")

    if membership is not None and membership.role == OrgMembership.Role.CLIENT:
        return _json_error("forbidden", status=403)

    if request.method == "GET":
        payload = _subtask_dict(subtask)

        project = subtask.task.epic.project
        custom_values_by_subtask_id = _custom_field_values_by_work_item_ids(
            project_id=project.id,
            work_item_type=CustomFieldValue.WorkItemType.SUBTASK,
            work_item_ids=[subtask.id],
            client_safe_only=False,
        )
        payload["custom_field_values"] = custom_values_by_subtask_id.get(subtask.id, [])
        workflow_ctx, workflow_ctx_reason = _workflow_progress_context_for_project(project)
        progress, why = compute_subtask_progress(
            project_workflow_id=project.workflow_id,
            workflow_ctx=workflow_ctx,
            workflow_ctx_reason=workflow_ctx_reason,
            workflow_stage_id=subtask.workflow_stage_id,
        )
        payload["progress"] = progress
        payload["progress_why"] = why
        return JsonResponse({"subtask": payload})

    if membership is not None and membership.role == OrgMembership.Role.CLIENT:
        return _json_error("forbidden", status=403)

    if request.method == "DELETE":
        subtask.delete()
        return JsonResponse({}, status=204)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    staged_prior_id = None
    staged_new_id = None
    if "workflow_stage_id" in payload:
        if membership is not None and membership.role not in {
            OrgMembership.Role.ADMIN,
            OrgMembership.Role.PM,
        }:
            return _json_error("forbidden", status=403)

        workflow_stage_id_raw = payload.get("workflow_stage_id")
        staged_prior_id = str(subtask.workflow_stage_id) if subtask.workflow_stage_id else None

        if workflow_stage_id_raw is None:
            subtask.workflow_stage = None
            staged_new_id = None
        else:
            project = subtask.task.epic.project
            if project.workflow_id is None:
                return _json_error("project has no workflow assigned", status=400)

            try:
                workflow_stage_uuid = uuid.UUID(str(workflow_stage_id_raw))
            except (TypeError, ValueError):
                return _json_error("workflow_stage_id must be a UUID or null", status=400)

            stage = WorkflowStage.objects.filter(
                id=workflow_stage_uuid, workflow_id=project.workflow_id
            ).first()
            if stage is None:
                return _json_error("invalid workflow_stage_id", status=400)

            subtask.workflow_stage = stage
            staged_new_id = str(stage.id)

    try:
        start_present, start_date = _parse_nullable_date_field(payload, "start_date")
        end_present, end_date = _parse_nullable_date_field(payload, "end_date")
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    if start_present or end_present:
        new_start = start_date if start_present else subtask.start_date
        new_end = end_date if end_present else subtask.end_date
        if new_start is not None and new_end is not None and new_start > new_end:
            return _json_error("start_date must be <= end_date", status=400)

    if "title" in payload:
        subtask.title = str(payload.get("title", "")).strip()
        if not subtask.title:
            return _json_error("title is required", status=400)

    if "description" in payload:
        subtask.description = str(payload.get("description", "")).strip()

    if "status" in payload:
        try:
            subtask.status = _require_status_param(payload.get("status")) or subtask.status
        except ValueError:
            return _json_error("invalid status", status=400)

    if start_present:
        subtask.start_date = start_date
    if end_present:
        subtask.end_date = end_date

    subtask.save()

    if "status" in payload:
        next_status = str(subtask.status or "")
        if prior_status != next_status:
            project = subtask.task.epic.project
            actor_user = membership.user if membership is not None else None
            emit_project_event(
                org=org,
                project=project,
                event_type=NotificationEventType.STATUS_CHANGED,
                actor_user=actor_user,
                data={
                    "work_item_type": "subtask",
                    "work_item_id": str(subtask.id),
                    "task_id": str(subtask.task_id),
                    "old_status": prior_status,
                    "new_status": next_status,
                },
                client_visible=bool(subtask.task.client_safe),
            )

    if "workflow_stage_id" in payload and staged_prior_id != staged_new_id:
        actor_user = membership.user if membership is not None else None
        principal_id = getattr(principal, "api_key_id", None) if principal is not None else None
        write_audit_event(
            org=org,
            actor_user=actor_user,
            event_type="subtask.workflow_stage_changed",
            metadata={
                "subtask_id": str(subtask.id),
                "task_id": str(subtask.task_id),
                "project_id": str(subtask.task.epic.project_id),
                "workflow_id": str(subtask.task.epic.project.workflow_id)
                if subtask.task.epic.project.workflow_id
                else None,
                "prior_workflow_stage_id": staged_prior_id,
                "workflow_stage_id": staged_new_id,
                "actor_type": "api_key" if principal is not None else "user",
                "actor_id": str(principal_id)
                if principal_id
                else str(actor_user.id)
                if actor_user
                else None,
            },
        )
        publish_org_event(
            org_id=org.id,
            event_type="work_item.updated",
            data={
                "project_id": str(subtask.task.epic.project_id),
                "epic_id": str(subtask.task.epic_id),
                "task_id": str(subtask.task_id),
                "subtask_id": str(subtask.id),
                "workflow_stage_id": str(subtask.workflow_stage_id)
                if subtask.workflow_stage_id
                else None,
                "reason": "workflow_stage_changed",
            },
        )

    project = subtask.task.epic.project
    workflow_ctx, workflow_ctx_reason = _workflow_progress_context_for_project(project)
    progress, why = compute_subtask_progress(
        project_workflow_id=project.workflow_id,
        workflow_ctx=workflow_ctx,
        workflow_ctx_reason=workflow_ctx_reason,
        workflow_stage_id=subtask.workflow_stage_id,
    )
    payload = _subtask_dict(subtask)
    custom_values_by_subtask_id = _custom_field_values_by_work_item_ids(
        project_id=project.id,
        work_item_type=CustomFieldValue.WorkItemType.SUBTASK,
        work_item_ids=[subtask.id],
        client_safe_only=False,
    )
    payload["custom_field_values"] = custom_values_by_subtask_id.get(subtask.id, [])
    payload["progress"] = progress
    payload["progress_why"] = why
    return JsonResponse({"subtask": payload})
