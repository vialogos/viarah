from __future__ import annotations

import json

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from identity.models import Org, OrgMembership

from .models import Epic, Project, Subtask, Task, WorkItemStatus


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
        "status": subtask.status,
        "created_at": subtask.created_at.isoformat(),
        "updated_at": subtask.updated_at.isoformat(),
    }


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

    if status_raw is not None:
        try:
            status = _require_status_param(status_raw) or WorkItemStatus.BACKLOG
        except ValueError:
            return _json_error("invalid status", status=400)
    else:
        status = WorkItemStatus.BACKLOG

    task = Task.objects.create(epic=epic, title=title, description=description, status=status)
    return JsonResponse({"task": _task_dict(task)})


@require_http_methods(["GET"])
def project_tasks_list_view(request: HttpRequest, org_id, project_id) -> JsonResponse:
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_work_items_membership(user, org.id)
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

    return JsonResponse({"tasks": [_task_dict(t) for t in tasks]})


@require_http_methods(["GET", "PATCH", "DELETE"])
def task_detail_view(request: HttpRequest, org_id, task_id) -> JsonResponse:
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_work_items_membership(user, org.id)
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
        return JsonResponse({"task": _task_dict(task)})

    if request.method == "DELETE":
        task.delete()
        return JsonResponse({}, status=204)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

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

    membership = _require_work_items_membership(user, org.id)
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
        return JsonResponse({"subtasks": [_subtask_dict(s) for s in subtasks]})

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    title = str(payload.get("title", "")).strip()
    description = str(payload.get("description", "")).strip()
    status_raw = payload.get("status")
    if not title:
        return _json_error("title is required", status=400)

    if status_raw is not None:
        try:
            status = _require_status_param(status_raw) or WorkItemStatus.BACKLOG
        except ValueError:
            return _json_error("invalid status", status=400)
    else:
        status = WorkItemStatus.BACKLOG

    subtask = Subtask.objects.create(task=task, title=title, description=description, status=status)
    return JsonResponse({"subtask": _subtask_dict(subtask)})


@require_http_methods(["GET", "PATCH", "DELETE"])
def subtask_detail_view(request: HttpRequest, org_id, subtask_id) -> JsonResponse:
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_work_items_membership(user, org.id)
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
        return JsonResponse({"subtask": _subtask_dict(subtask)})

    if request.method == "DELETE":
        subtask.delete()
        return JsonResponse({}, status=204)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

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

    subtask.save()
    return JsonResponse({"subtask": _subtask_dict(subtask)})
