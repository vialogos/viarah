from __future__ import annotations

import datetime
import json
import re
import uuid

from django.contrib.auth import get_user_model
from django.db.models import Prefetch
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from audit.services import write_audit_event
from collaboration.models import Comment
from customization.models import CustomFieldDefinition, CustomFieldValue
from identity.models import Org, OrgMembership, Person
from integrations.models import TaskGitLabLink
from notifications.models import NotificationEventType
from notifications.services import emit_assignment_changed, emit_project_event
from realtime.services import publish_org_event
from workflows.models import Workflow, WorkflowStage

from .models import (
    Epic,
    ProgressPolicy,
    Project,
    ProjectMembership,
    Subtask,
    Task,
    TaskParticipant,
    WorkItemStatus,
)
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


def _session_requires_project_membership(membership: OrgMembership | None) -> bool:
    return membership is not None and membership.role in {
        OrgMembership.Role.MEMBER,
        OrgMembership.Role.CLIENT,
    }


def _require_project_membership(
    membership: OrgMembership | None, project_id: uuid.UUID
) -> JsonResponse | None:
    """Enforce project membership for session MEMBER/CLIENT users.

    Org `admin`/`pm` users retain org-wide project access by default.
    API key principals are scoped separately via `ApiKey.project_id`.
    """

    if not _session_requires_project_membership(membership):
        return None

    if not ProjectMembership.objects.filter(
        project_id=project_id, user_id=membership.user_id
    ).exists():
        return _json_error("not found", status=404)

    return None


def _require_status_param(status_raw: str | None) -> str | None:
    if status_raw is None or not str(status_raw).strip():
        return None

    status = str(status_raw).strip()
    if status not in set(WorkItemStatus.values):
        raise ValueError("invalid status")
    return status


def _require_progress_policy(value_raw, *, allow_null: bool) -> str | None:
    if value_raw is None:
        return None if allow_null else ProgressPolicy.SUBTASKS_ROLLUP

    value = str(value_raw).strip()
    if not value:
        return None if allow_null else ProgressPolicy.SUBTASKS_ROLLUP

    if value not in set(ProgressPolicy.values):
        raise ValueError("invalid progress_policy")
    return value


def _require_progress_percent(value_raw, *, field: str) -> int | None:
    if value_raw is None:
        return None
    if isinstance(value_raw, bool):
        raise ValueError(f"{field} must be an integer 0..100 or null") from None
    try:
        value = int(value_raw)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be an integer 0..100 or null") from None
    if value < 0 or value > 100:
        raise ValueError(f"{field} must be between 0 and 100") from None
    return value


def _workflow_progress_context_for_project(
    project: Project,
) -> tuple[WorkflowProgressContext | None, str | None]:
    if project.workflow_id is None:
        return None, "project_missing_workflow"

    stages = list(
        WorkflowStage.objects.filter(workflow_id=project.workflow_id)
        .only("id", "order", "is_done", "category", "progress_percent")
        .order_by("order", "created_at", "id")
    )
    ctx, reason = build_workflow_progress_context(workflow_id=project.workflow_id, stages=stages)
    return ctx, reason


def _workflow_stage_meta(stage: WorkflowStage | None) -> dict | None:
    if stage is None:
        return None
    return {
        "id": str(stage.id),
        "name": stage.name,
        "order": int(stage.order),
        "category": str(getattr(stage, "category", "") or ""),
        "progress_percent": int(getattr(stage, "progress_percent", 0) or 0),
        "is_done": bool(stage.is_done),
        "is_qa": bool(stage.is_qa),
        "counts_as_wip": bool(stage.counts_as_wip),
    }


def _resolve_task_progress_policy(*, project: Project, epic: Epic, task: Task) -> tuple[str, str]:
    """
    Resolve the effective progress policy for a task, returning `(policy, source)`.

    Resolution order: Task override → Epic override → Project default.
    """

    if getattr(task, "progress_policy", None):
        return str(task.progress_policy), "task"
    if getattr(epic, "progress_policy", None):
        return str(epic.progress_policy), "epic"
    return str(getattr(project, "progress_policy", ProgressPolicy.SUBTASKS_ROLLUP)), "project"


def _resolve_epic_progress_policy(*, project: Project, epic: Epic) -> tuple[str, str]:
    if getattr(epic, "progress_policy", None):
        return str(epic.progress_policy), "epic"
    return str(getattr(project, "progress_policy", ProgressPolicy.SUBTASKS_ROLLUP)), "project"


def _compute_progress_from_workflow_stage(
    *,
    project_workflow_id: uuid.UUID | None,
    workflow_ctx: WorkflowProgressContext | None,
    workflow_ctx_reason: str | None,
    workflow_stage_id: uuid.UUID | None,
) -> tuple[float, dict]:
    why: dict = {
        "policy": "workflow_stage",
        "workflow_id": str(project_workflow_id) if project_workflow_id else None,
        "workflow_stage_id": str(workflow_stage_id) if workflow_stage_id else None,
    }

    if project_workflow_id is None:
        why["reason"] = "project_missing_workflow"
        return 0.0, why
    if workflow_ctx is None:
        why["reason"] = "workflow_context_unavailable"
        return 0.0, why
    if workflow_ctx_reason is not None:
        why["reason"] = workflow_ctx_reason
        return 0.0, why
    if workflow_stage_id is None:
        why["reason"] = "task_missing_workflow_stage"
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


def _compute_manual_progress(*, manual_progress_percent: int | None) -> tuple[float, dict]:
    why: dict = {
        "policy": "manual",
        "manual_progress_percent": manual_progress_percent,
    }
    if manual_progress_percent is None:
        why["reason"] = "manual_progress_missing"
        return 0.0, why
    clamped = max(0, min(int(manual_progress_percent), 100))
    if clamped != int(manual_progress_percent):
        why["reason"] = "manual_progress_percent_clamped"
    return float(clamped) / 100.0, why


def _compute_task_progress(
    *,
    project: Project,
    epic: Epic,
    task: Task,
    workflow_ctx: WorkflowProgressContext | None,
    workflow_ctx_reason: str | None,
    subtask_stage_ids: list[uuid.UUID | None],
) -> tuple[float, dict]:
    policy, source = _resolve_task_progress_policy(project=project, epic=epic, task=task)

    if policy == ProgressPolicy.WORKFLOW_STAGE:
        progress, why = _compute_progress_from_workflow_stage(
            project_workflow_id=project.workflow_id,
            workflow_ctx=workflow_ctx,
            workflow_ctx_reason=workflow_ctx_reason,
            workflow_stage_id=getattr(task, "workflow_stage_id", None),
        )
    elif policy == ProgressPolicy.MANUAL:
        progress, why = _compute_manual_progress(
            manual_progress_percent=getattr(task, "manual_progress_percent", None)
        )
    else:
        progress, why = compute_rollup_progress(
            project_workflow_id=project.workflow_id,
            workflow_ctx=workflow_ctx,
            workflow_ctx_reason=workflow_ctx_reason,
            workflow_stage_ids=subtask_stage_ids,
        )

    why["effective_policy"] = policy
    why["policy_source"] = source
    return progress, why


def _compute_epic_progress(
    *,
    project: Project,
    epic: Epic,
    workflow_ctx: WorkflowProgressContext | None,
    workflow_ctx_reason: str | None,
) -> tuple[float, dict]:
    policy, source = _resolve_epic_progress_policy(project=project, epic=epic)

    if policy == ProgressPolicy.MANUAL:
        progress, why = _compute_manual_progress(
            manual_progress_percent=getattr(epic, "manual_progress_percent", None)
        )
        why["effective_policy"] = policy
        why["policy_source"] = source
        return progress, why

    task_progresses: list[float] = []
    for task in epic.tasks.all():
        stage_ids = [s.workflow_stage_id for s in task.subtasks.all()]
        task_progress, _ = _compute_task_progress(
            project=project,
            epic=epic,
            task=task,
            workflow_ctx=workflow_ctx,
            workflow_ctx_reason=workflow_ctx_reason,
            subtask_stage_ids=stage_ids,
        )
        task_progresses.append(task_progress)

    why: dict = {
        "policy": "average_of_task_progress",
        "task_count": len(task_progresses),
        "effective_policy": policy,
        "policy_source": source,
    }
    if not task_progresses:
        why["reason"] = "no_tasks"
        return 0.0, why

    progress_sum = sum(task_progresses)
    why["task_progress_sum"] = progress_sum
    return progress_sum / float(len(task_progresses)), why


def _effective_task_status_for_epic_rollup(task: Task) -> str:
    stage = getattr(task, "workflow_stage", None)
    if stage is not None:
        if getattr(stage, "is_done", False):
            return WorkItemStatus.DONE
        if getattr(stage, "is_qa", False):
            return WorkItemStatus.QA
        if getattr(stage, "counts_as_wip", False):
            return WorkItemStatus.IN_PROGRESS
        return WorkItemStatus.BACKLOG

    status = str(getattr(task, "status", "") or "")
    if status in set(WorkItemStatus.values):
        return status
    return WorkItemStatus.BACKLOG


def _compute_epic_status(epic: Epic) -> str:
    """
    Compute epic status from task statuses/stages.

    Epics do not have an editable status; status is derived from underlying tasks.
    """

    tasks = list(epic.tasks.all())
    if not tasks:
        return WorkItemStatus.BACKLOG

    statuses = [_effective_task_status_for_epic_rollup(t) for t in tasks]
    total = len(statuses)
    done_count = sum(1 for s in statuses if s == WorkItemStatus.DONE)
    if done_count == total:
        return WorkItemStatus.DONE
    if WorkItemStatus.QA in statuses:
        return WorkItemStatus.QA
    if WorkItemStatus.IN_PROGRESS in statuses or done_count > 0:
        return WorkItemStatus.IN_PROGRESS
    return WorkItemStatus.BACKLOG


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
        "progress_policy": str(getattr(project, "progress_policy", ProgressPolicy.SUBTASKS_ROLLUP)),
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
        "status": _compute_epic_status(epic),
        "progress_policy": str(getattr(epic, "progress_policy", "") or "") or None,
        "manual_progress_percent": getattr(epic, "manual_progress_percent", None),
        "created_at": epic.created_at.isoformat(),
        "updated_at": epic.updated_at.isoformat(),
    }


def _task_dict(task: Task) -> dict:
    return {
        "id": str(task.id),
        "epic_id": str(task.epic_id),
        "workflow_stage_id": str(task.workflow_stage_id) if task.workflow_stage_id else None,
        "workflow_stage": _workflow_stage_meta(getattr(task, "workflow_stage", None)),
        "assignee_user_id": str(task.assignee_user_id) if task.assignee_user_id else None,
        "title": task.title,
        "description": task.description,
        "start_date": task.start_date.isoformat() if task.start_date else None,
        "end_date": task.end_date.isoformat() if task.end_date else None,
        "status": task.status,
        "progress_policy": str(getattr(task, "progress_policy", "") or "") or None,
        "manual_progress_percent": getattr(task, "manual_progress_percent", None),
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
        "workflow_stage_id": str(task.workflow_stage_id) if task.workflow_stage_id else None,
        "workflow_stage": _workflow_stage_meta(getattr(task, "workflow_stage", None)),
        "start_date": task.start_date.isoformat() if task.start_date else None,
        "end_date": task.end_date.isoformat() if task.end_date else None,
        "updated_at": task.updated_at.isoformat(),
    }


def _user_ref(user) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": getattr(user, "display_name", ""),
    }


def _person_ref(person: Person | None) -> dict | None:
    if person is None:
        return None
    return {
        "id": str(person.id),
        "full_name": person.full_name,
        "preferred_name": person.preferred_name,
        "title": person.title,
    }


def _task_participants_payload(*, org: Org, task: Task) -> list[dict]:
    """Build the participant set for a task (manual + auto sources)."""

    sources_by_user_id: dict[uuid.UUID, set[str]] = {}

    manual_user_ids = list(
        TaskParticipant.objects.filter(task=task)
        .values_list("user_id", flat=True)
        .order_by("created_at", "id")
    )
    for user_id in manual_user_ids:
        sources_by_user_id.setdefault(user_id, set()).add("manual")

    if task.assignee_user_id:
        sources_by_user_id.setdefault(task.assignee_user_id, set()).add("assignee")

    comment_author_ids = list(
        Comment.objects.filter(org=org, task=task)
        .values_list("author_user_id", flat=True)
        .distinct()
        .order_by("author_user_id")
    )
    for user_id in comment_author_ids:
        sources_by_user_id.setdefault(user_id, set()).add("comment")

    gitlab_usernames: set[str] = set()
    links = list(
        TaskGitLabLink.objects.filter(
            task=task,
            gitlab_type=TaskGitLabLink.GitLabType.ISSUE,
        )
        .only("cached_participants", "cached_assignees")
        .order_by("created_at", "id")
    )
    for link in links:
        for row in list(link.cached_participants or []):
            if not isinstance(row, dict):
                continue
            username = str(row.get("username", "")).strip().lower()
            if username:
                gitlab_usernames.add(username)
        for row in list(link.cached_assignees or []):
            if not isinstance(row, dict):
                continue
            username = str(row.get("username", "")).strip().lower()
            if username:
                gitlab_usernames.add(username)

    if gitlab_usernames:
        mapped_user_ids = list(
            Person.objects.filter(
                org=org,
                gitlab_username__in=sorted(gitlab_usernames),
                user_id__isnull=False,
            ).values_list("user_id", flat=True)
        )
        active_user_ids = set(
            OrgMembership.objects.filter(org=org, user_id__in=mapped_user_ids).values_list(
                "user_id", flat=True
            )
        )
        for user_id in active_user_ids:
            sources_by_user_id.setdefault(user_id, set()).add("gitlab")

    user_ids = list(sources_by_user_id.keys())
    if not user_ids:
        return []

    memberships = list(
        OrgMembership.objects.filter(org=org, user_id__in=user_ids)
        .select_related("user", "org")
        .order_by("created_at", "id")
    )
    membership_by_user_id = {m.user_id: m for m in memberships}

    missing_user_ids = [user_id for user_id in user_ids if user_id not in membership_by_user_id]
    user_model = get_user_model()
    users_by_id = {
        u.id: u
        for u in user_model.objects.filter(id__in=missing_user_ids).only(
            "id", "email", "display_name"
        )
    }

    people = list(
        Person.objects.filter(org=org, user_id__in=user_ids)
        .only("id", "user_id", "full_name", "preferred_name", "title")
        .order_by("created_at", "id")
    )
    person_by_user_id = {p.user_id: p for p in people if p.user_id is not None}

    payloads: list[dict] = []
    for user_id in user_ids:
        membership = membership_by_user_id.get(user_id)
        user = membership.user if membership is not None else users_by_id.get(user_id)
        if user is None:
            continue
        sources = sorted(sources_by_user_id.get(user_id, set()))
        payloads.append(
            {
                "user": _user_ref(user),
                "person": _person_ref(person_by_user_id.get(user_id)),
                "org_role": membership.role if membership is not None else None,
                "sources": sources,
            }
        )

    payloads.sort(
        key=lambda row: (str(row["user"].get("display_name") or ""), row["user"]["email"])
    )
    return payloads


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
    """List or create projects for an org.

    Auth: Session or API key (see `docs/api/scope-map.yaml` operations
    `work_items__projects_get` and `work_items__projects_post`).
    Inputs: Path `org_id`; POST JSON `{name, description?}`.
    Returns: `{projects: [...]}` for GET (client sessions receive a client-safe projection);
    `{project}` for POST.
    Side effects: POST creates a project. Project-restricted API keys cannot create projects.
    """
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

        if _session_requires_project_membership(membership):
            projects = projects.filter(memberships__user_id=membership.user_id)

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
    """Get, update, or delete a project.

    Auth: Session or API key (see `docs/api/scope-map.yaml` operations `work_items__project_get`,
    `work_items__project_patch`, and `work_items__project_delete`).
    Inputs: Path `org_id`, `project_id`; PATCH supports
    `{workflow_id?, progress_policy?, name?, description?}`.
    Returns: `{project}` (client-safe for session CLIENT); 204 for DELETE.
    Side effects: PATCH may write an audit event when assigning/changing `workflow_id`.
    """
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

    membership_err = _require_project_membership(membership, project.id)
    if membership_err is not None:
        return membership_err

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
            has_staged_tasks = Task.objects.filter(
                epic__project=project, workflow_stage__isnull=False
            ).exists()
            if has_staged_subtasks or has_staged_tasks:
                return _json_error(
                    "cannot change workflow while tasks/subtasks have workflow_stage_id set",
                    status=400,
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

    if "progress_policy" in payload:
        if membership is not None and membership.role not in {
            OrgMembership.Role.ADMIN,
            OrgMembership.Role.PM,
        }:
            return _json_error("forbidden", status=403)
        try:
            project.progress_policy = (
                _require_progress_policy(payload.get("progress_policy"), allow_null=False)
                or ProgressPolicy.SUBTASKS_ROLLUP
            )
        except ValueError:
            return _json_error("invalid progress_policy", status=400)
        fields_to_update.append("progress_policy")

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


def _project_membership_dict(project_membership: ProjectMembership, *, org_role: str) -> dict:
    user = project_membership.user
    return {
        "id": str(project_membership.id),
        "project_id": str(project_membership.project_id),
        "user": {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
        },
        "role": org_role,
        "created_at": project_membership.created_at.isoformat(),
    }


@require_http_methods(["GET", "POST"])
def project_memberships_collection_view(request: HttpRequest, org_id, project_id) -> JsonResponse:
    """List or add project memberships for a project.

    Auth: Session-only (ADMIN/PM) (see `docs/api/scope-map.yaml` operations
    `work_items__project_memberships_get` and `work_items__project_memberships_post`).
    Inputs:
      - Path `org_id`, `project_id`.
      - POST JSON `{user_id}`.
    Returns:
      - GET `{memberships: [...]}`.
      - POST `{membership}`.
    Side effects:
      - POST creates a `ProjectMembership` row and writes an audit event.
    """

    required_scope = "read" if request.method == "GET" else "write"
    org, membership, principal, err = _require_org_access(
        request,
        org_id,
        required_scope=required_scope,
        allow_client=False,
    )
    if err is not None:
        return err

    if principal is not None:
        return _json_error("forbidden", status=403)

    if membership is None or membership.role not in {
        OrgMembership.Role.ADMIN,
        OrgMembership.Role.PM,
    }:
        return _json_error("forbidden", status=403)

    project = Project.objects.filter(id=project_id, org=org).first()
    if project is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        rows = list(
            ProjectMembership.objects.filter(project=project)
            .select_related("user")
            .order_by("created_at")
        )
        user_ids = [row.user_id for row in rows]
        roles_by_user_id = {
            m.user_id: m.role
            for m in OrgMembership.objects.filter(org=org, user_id__in=user_ids).only(
                "user_id",
                "role",
            )
        }

        payloads = [
            _project_membership_dict(row, org_role=roles_by_user_id.get(row.user_id, ""))
            for row in rows
        ]
        return JsonResponse({"memberships": payloads})

    # POST
    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    raw_user_id = payload.get("user_id")
    if raw_user_id is None or str(raw_user_id).strip() == "":
        return _json_error("user_id is required", status=400)

    try:
        user_uuid = uuid.UUID(str(raw_user_id))
    except (TypeError, ValueError):
        return _json_error("user_id must be a UUID", status=400)

    org_membership = (
        OrgMembership.objects.filter(org=org, user_id=user_uuid)
        .only(
            "id",
            "role",
            "user_id",
        )
        .first()
    )
    if org_membership is None:
        return _json_error("user_id must be an org member", status=400)

    if ProjectMembership.objects.filter(project=project, user_id=user_uuid).exists():
        return _json_error("user is already a project member", status=400)

    project_membership = ProjectMembership.objects.create(project=project, user_id=user_uuid)

    write_audit_event(
        org=org,
        actor_user=request.user,
        event_type="project_membership.added",
        metadata={
            "project_id": str(project.id),
            "user_id": str(user_uuid),
            "org_role": str(org_membership.role),
        },
    )

    project_membership = (
        ProjectMembership.objects.filter(id=project_membership.id).select_related("user").first()
    )
    assert project_membership is not None

    return JsonResponse(
        {
            "membership": _project_membership_dict(
                project_membership,
                org_role=str(org_membership.role),
            )
        }
    )


@require_http_methods(["DELETE"])
def project_membership_detail_view(
    request: HttpRequest, org_id, project_id, membership_id
) -> JsonResponse:
    """Remove a project membership.

    Auth: Session-only (ADMIN/PM) (see `docs/api/scope-map.yaml` operation
    `work_items__project_membership_delete`).
    Inputs: Path `org_id`, `project_id`, `membership_id`.
    Returns: 204.
    Side effects: Deletes the membership and writes an audit event.
    """

    org, membership, principal, err = _require_org_access(
        request,
        org_id,
        required_scope="write",
        allow_client=False,
    )
    if err is not None:
        return err

    if principal is not None:
        return _json_error("forbidden", status=403)

    if membership is None or membership.role not in {
        OrgMembership.Role.ADMIN,
        OrgMembership.Role.PM,
    }:
        return _json_error("forbidden", status=403)

    project_membership = (
        ProjectMembership.objects.filter(
            id=membership_id,
            project_id=project_id,
            project__org=org,
        )
        .select_related("project")
        .first()
    )
    if project_membership is None:
        return _json_error("not found", status=404)

    removed_user_id = str(project_membership.user_id)
    project_membership.delete()

    write_audit_event(
        org=org,
        actor_user=request.user,
        event_type="project_membership.removed",
        metadata={
            "project_id": str(project_id),
            "user_id": removed_user_id,
        },
    )

    return JsonResponse({}, status=204)


@require_http_methods(["GET", "POST"])
def project_epics_collection_view(request: HttpRequest, org_id, project_id) -> JsonResponse:
    """List or create epics for a project.

    Auth: Session or API key (see `docs/api/scope-map.yaml` operations
    `work_items__project_epics_get` and `work_items__project_epics_post`).
    Inputs: Path `org_id`, `project_id`; POST JSON `{title, description?, status?}`.
    Returns: `{epics: [...]}` for GET (includes computed progress rollups); `{epic}` for POST.
    Side effects: POST creates an epic. Epic scheduling fields are intentionally unsupported.
    """
    required_scope = "read" if request.method == "GET" else "write"
    org, membership, principal, err = _require_org_access(
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

    membership_err = _require_project_membership(membership, project.id)
    if membership_err is not None:
        return membership_err

    if request.method == "GET":
        workflow_ctx, workflow_ctx_reason = _workflow_progress_context_for_project(project)
        task_prefetch = Prefetch(
            "tasks",
            queryset=Task.objects.only(
                "id",
                "epic_id",
                "workflow_stage_id",
                "status",
                "progress_policy",
                "manual_progress_percent",
            )
            .select_related("workflow_stage")
            .prefetch_related(
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
            progress, why = _compute_epic_progress(
                project=project,
                epic=epic,
                workflow_ctx=workflow_ctx,
                workflow_ctx_reason=workflow_ctx_reason,
            )

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
    if not title:
        return _json_error("title is required", status=400)

    if "status" in payload:
        return _json_error("epic status is computed and cannot be set", status=400)

    progress_policy = None
    if "progress_policy" in payload:
        if membership is not None and membership.role not in {
            OrgMembership.Role.ADMIN,
            OrgMembership.Role.PM,
        }:
            return _json_error("forbidden", status=403)
        try:
            progress_policy = _require_progress_policy(payload.get("progress_policy"), allow_null=True)
        except ValueError:
            return _json_error("invalid progress_policy", status=400)
        if progress_policy == ProgressPolicy.MANUAL:
            return _json_error("invalid progress_policy", status=400)

    epic = Epic.objects.create(
        project=project,
        title=title,
        description=description,
        progress_policy=progress_policy,
    )
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
    """Get, update, or delete an epic.

    Auth: Session or API key (see `docs/api/scope-map.yaml` operations `work_items__epic_get`,
    `work_items__epic_patch`, and `work_items__epic_delete`).
    Inputs: Path `org_id`, `epic_id`; PATCH supports `{title?, description?, status?}`.
    Returns: `{epic}` (includes computed progress rollups); 204 for DELETE.
    Side effects: PATCH updates epic fields; epic scheduling fields are intentionally unsupported.
    """
    required_scope = "read" if request.method == "GET" else "write"
    org, membership, principal, err = _require_org_access(
        request, org_id, required_scope=required_scope, allow_client=False
    )
    if err is not None:
        return err

    task_prefetch = Prefetch(
        "tasks",
        queryset=Task.objects.only(
            "id",
            "epic_id",
            "workflow_stage_id",
            "status",
            "progress_policy",
            "manual_progress_percent",
        )
        .select_related("workflow_stage")
        .prefetch_related(
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

    membership_err = _require_project_membership(membership, epic.project_id)
    if membership_err is not None:
        return membership_err

    if request.method == "GET":
        workflow_ctx, workflow_ctx_reason = _workflow_progress_context_for_project(epic.project)
        progress, why = _compute_epic_progress(
            project=epic.project,
            epic=epic,
            workflow_ctx=workflow_ctx,
            workflow_ctx_reason=workflow_ctx_reason,
        )

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
        return _json_error("epic status is computed and cannot be set", status=400)

    if "progress_policy" in payload:
        if membership is not None and membership.role not in {
            OrgMembership.Role.ADMIN,
            OrgMembership.Role.PM,
        }:
            return _json_error("forbidden", status=403)
        try:
            epic.progress_policy = _require_progress_policy(
                payload.get("progress_policy"), allow_null=True
            )
        except ValueError:
            return _json_error("invalid progress_policy", status=400)

    if "manual_progress_percent" in payload:
        if membership is not None and membership.role not in {
            OrgMembership.Role.ADMIN,
            OrgMembership.Role.PM,
        }:
            return _json_error("forbidden", status=403)
        try:
            epic.manual_progress_percent = _require_progress_percent(
                payload.get("manual_progress_percent"), field="manual_progress_percent"
            )
        except ValueError as exc:
            return _json_error(str(exc), status=400)

    epic.save()
    workflow_ctx, workflow_ctx_reason = _workflow_progress_context_for_project(epic.project)
    progress, why = _compute_epic_progress(
        project=epic.project,
        epic=epic,
        workflow_ctx=workflow_ctx,
        workflow_ctx_reason=workflow_ctx_reason,
    )

    payload = _epic_dict(epic)
    payload["progress"] = progress
    payload["progress_why"] = why
    return JsonResponse({"epic": payload})


@require_http_methods(["POST"])
def epic_tasks_collection_view(request: HttpRequest, org_id, epic_id) -> JsonResponse:
    """Create a task within an epic.

    Auth: Session or API key (write) (see `docs/api/scope-map.yaml` operation
    `work_items__epic_tasks_post`).
    Inputs: Path `org_id`, `epic_id`; JSON `{title, description?, status?, start_date?, end_date?}`.
    Returns: `{task}` (includes computed progress rollups).
    Side effects: Creates a task row.
    """
    org, membership, principal, err = _require_org_access(
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

    membership_err = _require_project_membership(membership, epic.project_id)
    if membership_err is not None:
        return membership_err

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
    workflow_ctx, workflow_ctx_reason = _workflow_progress_context_for_project(epic.project)
    progress, why = _compute_task_progress(
        project=epic.project,
        epic=epic,
        task=task,
        workflow_ctx=workflow_ctx,
        workflow_ctx_reason=workflow_ctx_reason,
        subtask_stage_ids=[],
    )
    payload = _task_dict(Task.objects.select_related("workflow_stage").get(id=task.id))
    payload["custom_field_values"] = []
    payload["progress"] = progress
    payload["progress_why"] = why
    return JsonResponse({"task": payload})


@require_http_methods(["GET"])
def project_tasks_list_view(request: HttpRequest, org_id, project_id) -> JsonResponse:
    """List tasks for a project (flattened list) with progress and custom-field values.

    Auth: Session or API key (read) (see `docs/api/scope-map.yaml` operation
    `work_items__project_tasks_get`).
    Inputs: Path `org_id`, `project_id`; optional query `status`, `assignee_user_id`.
    Returns: `{last_updated_at, tasks: [...]}`; session CLIENT principals receive a client-safe
    projection.
    Side effects: None.
    """
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

    membership_err = _require_project_membership(membership, project.id)
    if membership_err is not None:
        return membership_err

    workflow_ctx, workflow_ctx_reason = _workflow_progress_context_for_project(project)

    status_raw = request.GET.get("status")
    try:
        status = _require_status_param(status_raw)
    except ValueError:
        return _json_error("invalid status", status=400)

    assignee_raw = request.GET.get("assignee_user_id")
    assignee_uuid: uuid.UUID | None = None
    if assignee_raw is not None and str(assignee_raw).strip():
        normalized = str(assignee_raw).strip().lower()
        if normalized == "me":
            if principal is not None:
                try:
                    assignee_uuid = uuid.UUID(str(getattr(principal, "owner_user_id", "")))
                except (TypeError, ValueError):
                    return _json_error("invalid principal owner_user_id", status=400)
            elif membership is not None:
                assignee_uuid = membership.user_id
            else:
                return _json_error("unauthorized", status=401)
        else:
            try:
                assignee_uuid = uuid.UUID(str(assignee_raw))
            except (TypeError, ValueError):
                return _json_error("assignee_user_id must be a UUID or 'me'", status=400)

    tasks = Task.objects.filter(epic__project_id=project.id, epic__project__org_id=org.id)
    client_safe_only = membership is not None and membership.role == OrgMembership.Role.CLIENT
    if client_safe_only:
        tasks = tasks.filter(client_safe=True)
    if status is not None:
        tasks = tasks.filter(status=status)
    if assignee_uuid is not None:
        tasks = tasks.filter(assignee_user_id=assignee_uuid)
    tasks = tasks.select_related("epic", "epic__project", "workflow_stage").prefetch_related(
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
            progress, why = _compute_task_progress(
                project=project,
                epic=task.epic,
                task=task,
                workflow_ctx=workflow_ctx,
                workflow_ctx_reason=workflow_ctx_reason,
                subtask_stage_ids=stage_ids,
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
        progress, why = _compute_task_progress(
            project=project,
            epic=task.epic,
            task=task,
            workflow_ctx=workflow_ctx,
            workflow_ctx_reason=workflow_ctx_reason,
            subtask_stage_ids=stage_ids,
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
    """Get, update, or delete a task.

    Auth: Session or API key (see `docs/api/scope-map.yaml` operations `work_items__task_get`,
    `work_items__task_patch`, and `work_items__task_delete`).
    Inputs: Path `org_id`, `task_id`; PATCH supports title/description, assignee, scheduling,
    `client_safe` (session ADMIN/PM only), progress overrides, and `workflow_stage_id` (session
    ADMIN/PM only).
    Returns: `{task}` (includes progress and custom-field values); 204 for DELETE.
    Side effects: PATCH may emit notification events (assignment/status changes).
    """
    required_scope = "read" if request.method == "GET" else "write"
    org, membership, principal, err = _require_org_access(
        request, org_id, required_scope=required_scope, allow_client=True
    )
    if err is not None:
        return err

    task_qs = (
        Task.objects.filter(id=task_id, epic__project__org_id=org.id)
        .select_related("epic", "epic__project", "workflow_stage")
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

    membership_err = _require_project_membership(membership, project.id)
    if membership_err is not None:
        return membership_err

    prior_status = str(task.status or "")
    prior_assignee_user_id = str(task.assignee_user_id) if task.assignee_user_id else None
    staged_prior_id = str(task.workflow_stage_id) if task.workflow_stage_id else None

    workflow_ctx, workflow_ctx_reason = _workflow_progress_context_for_project(project)

    if request.method == "GET":
        stage_ids = [s.workflow_stage_id for s in task.subtasks.all()]
        task_progress, task_progress_why = _compute_task_progress(
            project=project,
            epic=task.epic,
            task=task,
            workflow_ctx=workflow_ctx,
            workflow_ctx_reason=workflow_ctx_reason,
            subtask_stage_ids=stage_ids,
        )
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

    staged_new_id = staged_prior_id
    stage_change_updates_status = False
    if "workflow_stage_id" in payload:
        if membership is not None and membership.role not in {
            OrgMembership.Role.ADMIN,
            OrgMembership.Role.PM,
        }:
            return _json_error("forbidden", status=403)

        workflow_stage_id_raw = payload.get("workflow_stage_id")

        if workflow_stage_id_raw is None:
            task.workflow_stage = None
            staged_new_id = None
        else:
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

            task.workflow_stage = stage
            staged_new_id = str(stage.id)

            if str(task.status) != str(stage.category):
                task.status = str(stage.category)
                stage_change_updates_status = True

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
        if task.workflow_stage_id is not None or staged_new_id is not None:
            return _json_error(
                "status is derived from workflow_stage.category when workflow_stage_id is set",
                status=400,
            )
        try:
            task.status = _require_status_param(payload.get("status")) or task.status
        except ValueError:
            return _json_error("invalid status", status=400)

    if "progress_policy" in payload:
        if membership is not None and membership.role not in {
            OrgMembership.Role.ADMIN,
            OrgMembership.Role.PM,
        }:
            return _json_error("forbidden", status=403)
        try:
            task.progress_policy = _require_progress_policy(
                payload.get("progress_policy"), allow_null=True
            )
        except ValueError:
            return _json_error("invalid progress_policy", status=400)

    if "manual_progress_percent" in payload:
        if membership is not None and membership.role not in {
            OrgMembership.Role.ADMIN,
            OrgMembership.Role.PM,
        }:
            return _json_error("forbidden", status=403)
        try:
            task.manual_progress_percent = _require_progress_percent(
                payload.get("manual_progress_percent"), field="manual_progress_percent"
            )
        except ValueError as exc:
            return _json_error(str(exc), status=400)

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

            if not ProjectMembership.objects.filter(
                project_id=project.id, user_id=assignee_uuid
            ).exists():
                return _json_error(
                    "assignee_user_id must be a project member",
                    status=400,
                )

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

    if "status" in payload or stage_change_updates_status:
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

    if "workflow_stage_id" in payload and staged_prior_id != staged_new_id:
        actor_user = membership.user if membership is not None else None
        principal_id = getattr(principal, "api_key_id", None) if principal is not None else None
        write_audit_event(
            org=org,
            actor_user=actor_user,
            event_type="task.workflow_stage_changed",
            metadata={
                "task_id": str(task.id),
                "epic_id": str(task.epic_id),
                "project_id": str(project.id),
                "workflow_id": str(project.workflow_id) if project.workflow_id else None,
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
                "project_id": str(project.id),
                "epic_id": str(task.epic_id),
                "task_id": str(task.id),
                "workflow_stage_id": str(task.workflow_stage_id)
                if task.workflow_stage_id
                else None,
                "reason": "workflow_stage_changed",
            },
        )

    stage_ids = [s.workflow_stage_id for s in task.subtasks.all()]
    task_progress, task_progress_why = _compute_task_progress(
        project=project,
        epic=task.epic,
        task=task,
        workflow_ctx=workflow_ctx,
        workflow_ctx_reason=workflow_ctx_reason,
        subtask_stage_ids=stage_ids,
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
def task_participants_collection_view(request: HttpRequest, org_id, task_id) -> JsonResponse:
    """List or add manual participants for a task.

    Auth:
      - GET: Session or API key (read) (see `docs/api/scope-map.yaml` operation
        `work_items__task_participants_get`).
      - POST: Session-only (ADMIN/PM) (see `docs/api/scope-map.yaml` operation
        `work_items__task_participants_post`).
    Inputs:
      - Path `org_id`, `task_id`.
      - POST JSON `{user_id}`.
    Returns:
      - GET `{participants: [...]}` where each participant includes
        `{user, person?, org_role, sources}`.
      - POST `{participant}` (manual participant create is idempotent).
    Side effects:
      - POST creates a `TaskParticipant` row when needed and writes an audit event.
    """

    required_scope = "read" if request.method == "GET" else "write"
    org, membership, principal, err = _require_org_access(
        request,
        org_id,
        required_scope=required_scope,
        allow_client=request.method == "GET",
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

    project = task.epic.project
    membership_err = _require_project_membership(membership, project.id)
    if membership_err is not None:
        return membership_err

    client_safe_only = membership is not None and membership.role == OrgMembership.Role.CLIENT
    if client_safe_only and not task.client_safe:
        return _json_error("not found", status=404)

    if request.method == "GET":
        return JsonResponse({"participants": _task_participants_payload(org=org, task=task)})

    if principal is not None:
        return _json_error("forbidden", status=403)

    if membership is None or membership.role not in {
        OrgMembership.Role.ADMIN,
        OrgMembership.Role.PM,
    }:
        return _json_error("forbidden", status=403)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    user_id_raw = payload.get("user_id", None)
    try:
        target_user_id = uuid.UUID(str(user_id_raw))
    except (TypeError, ValueError):
        return _json_error("user_id must be a UUID", status=400)

    target_membership = (
        OrgMembership.objects.filter(org=org, user_id=target_user_id).select_related("user").first()
    )
    if target_membership is None:
        return _json_error("user_id must be an org member", status=400)

    if (
        target_membership.role
        in {
            OrgMembership.Role.MEMBER,
            OrgMembership.Role.CLIENT,
        }
        and not ProjectMembership.objects.filter(project=project, user_id=target_user_id).exists()
    ):
        return _json_error("user_id must be a project member", status=400)

    participant, created = TaskParticipant.objects.get_or_create(
        task=task,
        user_id=target_user_id,
        defaults={"created_by_user": membership.user},
    )
    if created:
        write_audit_event(
            org=org,
            actor_user=membership.user,
            event_type="task.participant.added",
            metadata={"task_id": str(task.id), "user_id": str(target_user_id)},
        )

    return JsonResponse(
        {
            "participant": {
                "task_id": str(task.id),
                "user_id": str(participant.user_id),
                "created_at": participant.created_at.isoformat(),
            }
        },
        status=201 if created else 200,
    )


@require_http_methods(["DELETE"])
def task_participant_detail_view(request: HttpRequest, org_id, task_id, user_id) -> JsonResponse:
    """Remove a manual participant from a task.

    Auth: Session-only (ADMIN/PM) (see `docs/api/scope-map.yaml` operation
    `work_items__task_participant_delete`).
    Inputs: Path `org_id`, `task_id`, `user_id`.
    Returns: 204 No Content.
    Side effects: Deletes a `TaskParticipant` row and writes an audit event when a row existed.
    """

    org, membership, principal, err = _require_org_access(
        request,
        org_id,
        required_scope="write",
        allow_client=False,
    )
    if err is not None:
        return err

    if principal is not None:
        return _json_error("forbidden", status=403)

    if membership is None or membership.role not in {
        OrgMembership.Role.ADMIN,
        OrgMembership.Role.PM,
    }:
        return _json_error("forbidden", status=403)

    task = (
        Task.objects.filter(id=task_id, epic__project__org_id=org.id)
        .select_related("epic", "epic__project")
        .first()
    )
    if task is None:
        return _json_error("not found", status=404)

    membership_err = _require_project_membership(membership, task.epic.project_id)
    if membership_err is not None:
        return membership_err

    try:
        target_user_id = uuid.UUID(str(user_id))
    except (TypeError, ValueError):
        return _json_error("user_id must be a UUID", status=400)

    deleted = TaskParticipant.objects.filter(task=task, user_id=target_user_id).delete()
    if deleted[0]:
        write_audit_event(
            org=org,
            actor_user=membership.user,
            event_type="task.participant.removed",
            metadata={"task_id": str(task.id), "user_id": str(target_user_id)},
        )
    return JsonResponse({}, status=204)


@require_http_methods(["GET", "POST"])
def task_subtasks_collection_view(request: HttpRequest, org_id, task_id) -> JsonResponse:
    """List or create subtasks for a task.

    Auth: Session or API key (see `docs/api/scope-map.yaml` operations
    `work_items__task_subtasks_get` and `work_items__task_subtasks_post`).
    Note: session CLIENT principals are currently rejected.
    Inputs: Path `org_id`, `task_id`; optional query `status`; POST JSON supports title/description,
    status, and scheduling dates.
    Returns: `{subtasks: [...]}` for GET (includes per-subtask progress); `{subtask}` for POST.
    Side effects: POST creates a subtask row.
    """
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

    membership_err = _require_project_membership(membership, task.epic.project_id)
    if membership_err is not None:
        return membership_err

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
    """Get, update, or delete a subtask.

    Auth: Session or API key (see `docs/api/scope-map.yaml` operations `work_items__subtask_get`,
    `work_items__subtask_patch`, and `work_items__subtask_delete`). Note: session CLIENT principals
    are currently rejected.
    Inputs: Path `org_id`, `subtask_id`; PATCH supports title/description/status/scheduling and
    `workflow_stage_id` (session ADMIN/PM only).
    Returns: `{subtask}` (includes progress and custom-field values); 204 for DELETE.
    Side effects: PATCH may emit notification events; workflow-stage changes write an audit event
    and publish a realtime org event.
    """
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

    membership_err = _require_project_membership(membership, subtask.task.epic.project_id)
    if membership_err is not None:
        return membership_err

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
    stage_change_updates_status = False
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
            if str(subtask.status) != str(stage.category):
                subtask.status = str(stage.category)
                stage_change_updates_status = True

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
        if subtask.workflow_stage_id is not None or staged_new_id is not None:
            return _json_error(
                "status is derived from workflow_stage.category when workflow_stage_id is set",
                status=400,
            )
        try:
            subtask.status = _require_status_param(payload.get("status")) or subtask.status
        except ValueError:
            return _json_error("invalid status", status=400)

    if start_present:
        subtask.start_date = start_date
    if end_present:
        subtask.end_date = end_date

    subtask.save()

    if "status" in payload or stage_change_updates_status:
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
