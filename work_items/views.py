from __future__ import annotations

import datetime
import json
import re

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from identity.models import Org, OrgMembership

from .models import Epic, Project, Subtask, Task, WorkItemStatus

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


def _require_status_param(status_raw: str | None) -> str | None:
    if status_raw is None or not str(status_raw).strip():
        return None

    status = str(status_raw).strip()
    if status not in set(WorkItemStatus.values):
        raise ValueError("invalid status")
    return status


def _project_dict(project: Project) -> dict:
    return {
        "id": str(project.id),
        "org_id": str(project.org_id),
        "name": project.name,
        "description": project.description,
        "created_at": project.created_at.isoformat(),
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
        "title": task.title,
        "description": task.description,
        "start_date": task.start_date.isoformat() if task.start_date else None,
        "end_date": task.end_date.isoformat() if task.end_date else None,
        "status": task.status,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def _subtask_dict(subtask: Subtask) -> dict:
    return {
        "id": str(subtask.id),
        "task_id": str(subtask.task_id),
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
    }


def _subtask_client_safe_dict(subtask: Subtask) -> dict:
    return {
        "id": str(subtask.id),
        "task_id": str(subtask.task_id),
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
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_work_items_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    if request.method == "GET":
        projects = Project.objects.filter(org=org).order_by("created_at")
        return JsonResponse({"projects": [_project_dict(p) for p in projects]})

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
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_work_items_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    project = Project.objects.filter(id=project_id, org=org).first()
    if project is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        return JsonResponse({"project": _project_dict(project)})

    if request.method == "DELETE":
        project.delete()
        return JsonResponse({}, status=204)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    if "name" in payload:
        project.name = str(payload.get("name", "")).strip()
        if not project.name:
            return _json_error("name is required", status=400)

    if "description" in payload:
        project.description = str(payload.get("description", "")).strip()

    project.save()
    return JsonResponse({"project": _project_dict(project)})


@require_http_methods(["GET", "POST"])
def project_epics_collection_view(request: HttpRequest, org_id, project_id) -> JsonResponse:
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_work_items_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    project = Project.objects.filter(id=project_id, org=org).first()
    if project is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        epics = Epic.objects.filter(project=project).order_by("created_at")
        return JsonResponse({"epics": [_epic_dict(e) for e in epics]})

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
    return JsonResponse({"epic": _epic_dict(epic)})


@require_http_methods(["GET", "PATCH", "DELETE"])
def epic_detail_view(request: HttpRequest, org_id, epic_id) -> JsonResponse:
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_work_items_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    epic = Epic.objects.filter(id=epic_id, project__org_id=org.id).select_related("project").first()
    if epic is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        return JsonResponse({"epic": _epic_dict(epic)})

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
    return JsonResponse({"epic": _epic_dict(epic)})


@require_http_methods(["POST"])
def epic_tasks_collection_view(request: HttpRequest, org_id, epic_id) -> JsonResponse:
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_work_items_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    epic = Epic.objects.filter(id=epic_id, project__org_id=org.id).select_related("project").first()
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
    return JsonResponse({"task": _task_dict(task)})


@require_http_methods(["GET"])
def project_tasks_list_view(request: HttpRequest, org_id, project_id) -> JsonResponse:
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_work_items_read_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    project = Project.objects.filter(id=project_id, org_id=org.id).first()
    if project is None:
        return _json_error("not found", status=404)

    status_raw = request.GET.get("status")
    try:
        status = _require_status_param(status_raw)
    except ValueError:
        return _json_error("invalid status", status=400)

    tasks = Task.objects.filter(epic__project_id=project.id, epic__project__org_id=org.id)
    if status is not None:
        tasks = tasks.filter(status=status)
    tasks = tasks.select_related("epic").order_by("created_at")

    if membership.role == OrgMembership.Role.CLIENT:
        return JsonResponse({"tasks": [_task_client_safe_dict(t) for t in tasks]})

    return JsonResponse({"tasks": [_task_dict(t) for t in tasks]})


@require_http_methods(["GET", "PATCH", "DELETE"])
def task_detail_view(request: HttpRequest, org_id, task_id) -> JsonResponse:
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_work_items_read_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    task = (
        Task.objects.filter(id=task_id, epic__project__org_id=org.id)
        .select_related("epic", "epic__project")
        .first()
    )
    if task is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        if membership.role == OrgMembership.Role.CLIENT:
            return JsonResponse({"task": _task_client_safe_dict(task)})
        return JsonResponse({"task": _task_dict(task)})

    if membership.role == OrgMembership.Role.CLIENT:
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

    if start_present:
        task.start_date = start_date
    if end_present:
        task.end_date = end_date

    task.save()
    return JsonResponse({"task": _task_dict(task)})


@require_http_methods(["GET", "POST"])
def task_subtasks_collection_view(request: HttpRequest, org_id, task_id) -> JsonResponse:
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_work_items_read_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    task = (
        Task.objects.filter(id=task_id, epic__project__org_id=org.id).select_related("epic").first()
    )
    if task is None:
        return _json_error("not found", status=404)

    status_raw = request.GET.get("status")
    try:
        status = _require_status_param(status_raw)
    except ValueError:
        return _json_error("invalid status", status=400)

    if request.method == "GET":
        subtasks = Subtask.objects.filter(task=task)
        if status is not None:
            subtasks = subtasks.filter(status=status)
        subtasks = subtasks.order_by("created_at")
        if membership.role == OrgMembership.Role.CLIENT:
            return JsonResponse({"subtasks": [_subtask_client_safe_dict(s) for s in subtasks]})
        return JsonResponse({"subtasks": [_subtask_dict(s) for s in subtasks]})

    if membership.role == OrgMembership.Role.CLIENT:
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
    return JsonResponse({"subtask": _subtask_dict(subtask)})


@require_http_methods(["GET", "PATCH", "DELETE"])
def subtask_detail_view(request: HttpRequest, org_id, subtask_id) -> JsonResponse:
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_work_items_read_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    subtask = (
        Subtask.objects.filter(id=subtask_id, task__epic__project__org_id=org.id)
        .select_related("task", "task__epic")
        .first()
    )
    if subtask is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        if membership.role == OrgMembership.Role.CLIENT:
            return JsonResponse({"subtask": _subtask_client_safe_dict(subtask)})
        return JsonResponse({"subtask": _subtask_dict(subtask)})

    if membership.role == OrgMembership.Role.CLIENT:
        return _json_error("forbidden", status=403)

    if request.method == "DELETE":
        subtask.delete()
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
    return JsonResponse({"subtask": _subtask_dict(subtask)})
