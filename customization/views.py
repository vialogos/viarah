from __future__ import annotations

import json
import uuid

from django.db import IntegrityError, transaction
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from audit.services import write_audit_event
from identity.models import Org, OrgMembership
from work_items.models import Project, Subtask, Task

from .models import CustomFieldDefinition, CustomFieldValue, SavedView
from .services import (
    normalize_custom_field_options,
    normalize_saved_view_filters,
    normalize_saved_view_group_by,
    normalize_saved_view_sort,
    validate_custom_field_value,
)


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


def _require_org(org_id) -> Org | None:
    return Org.objects.filter(id=org_id).first()


def _require_org_read_membership(user, org_id) -> OrgMembership | None:
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


def _require_org_pm_membership(user, org_id) -> OrgMembership | None:
    membership = (
        OrgMembership.objects.filter(user=user, org_id=org_id).select_related("org").first()
    )
    if membership is None:
        return None
    if membership.role not in {OrgMembership.Role.ADMIN, OrgMembership.Role.PM}:
        return None
    return membership


def _saved_view_dict(view: SavedView) -> dict:
    return {
        "id": str(view.id),
        "org_id": str(view.org_id),
        "project_id": str(view.project_id),
        "owner_user_id": str(view.owner_user_id),
        "name": view.name,
        "client_safe": bool(view.client_safe),
        "filters": view.filters or {},
        "sort": view.sort or {},
        "group_by": view.group_by,
        "created_at": view.created_at.isoformat(),
        "updated_at": view.updated_at.isoformat(),
    }


def _custom_field_def_dict(field: CustomFieldDefinition) -> dict:
    return {
        "id": str(field.id),
        "org_id": str(field.org_id),
        "project_id": str(field.project_id),
        "name": field.name,
        "field_type": field.field_type,
        "options": list(field.options or []),
        "client_safe": bool(field.client_safe),
        "created_at": field.created_at.isoformat(),
        "updated_at": field.updated_at.isoformat(),
        "archived_at": field.archived_at.isoformat() if field.archived_at else None,
    }


def _custom_field_value_dict(value: CustomFieldValue) -> dict:
    return {"field_id": str(value.field_id), "value": value.value_json}


@require_http_methods(["GET", "POST"])
def saved_views_collection_view(request: HttpRequest, org_id, project_id) -> JsonResponse:
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_org_read_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    project = Project.objects.filter(id=project_id, org_id=org.id).first()
    if project is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        views = SavedView.objects.filter(
            org_id=org.id,
            project_id=project.id,
            owner_user_id=user.id,
            archived_at__isnull=True,
        ).order_by("created_at")

        if membership.role == OrgMembership.Role.CLIENT:
            views = views.filter(client_safe=True)

        return JsonResponse({"saved_views": [_saved_view_dict(v) for v in views]})

    # POST
    membership = _require_org_pm_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    name = str(payload.get("name", "")).strip()
    if not name:
        return _json_error("name is required", status=400)

    try:
        filters = normalize_saved_view_filters(payload.get("filters"))
        sort = normalize_saved_view_sort(payload.get("sort"))
        group_by = normalize_saved_view_group_by(payload.get("group_by"))
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    client_safe = bool(payload.get("client_safe", False))

    with transaction.atomic():
        try:
            view = SavedView.objects.create(
                org=org,
                project=project,
                owner_user=user,
                name=name,
                client_safe=client_safe,
                filters=filters,
                sort=sort,
                group_by=group_by,
            )
        except IntegrityError:
            return _json_error("a saved view with this name already exists", status=400)

    write_audit_event(
        org=org,
        actor_user=user,
        event_type="saved_view.created",
        metadata={
            "saved_view_id": str(view.id),
            "org_id": str(org.id),
            "project_id": str(project.id),
            "owner_user_id": str(user.id),
            "client_safe": bool(view.client_safe),
        },
    )

    return JsonResponse({"saved_view": _saved_view_dict(view)})


@require_http_methods(["PATCH", "DELETE"])
def saved_view_detail_view(request: HttpRequest, org_id, saved_view_id) -> JsonResponse:
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_org_pm_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    saved_view = (
        SavedView.objects.filter(
            id=saved_view_id, org_id=org.id, owner_user_id=user.id, archived_at__isnull=True
        )
        .select_related("project")
        .first()
    )
    if saved_view is None:
        return _json_error("not found", status=404)

    if request.method == "DELETE":
        saved_view.archived_at = timezone.now()
        saved_view.save(update_fields=["archived_at", "updated_at"])
        write_audit_event(
            org=org,
            actor_user=user,
            event_type="saved_view.archived",
            metadata={
                "saved_view_id": str(saved_view.id),
                "org_id": str(org.id),
                "project_id": str(saved_view.project_id),
                "owner_user_id": str(user.id),
            },
        )
        return JsonResponse({}, status=204)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    fields_to_update: list[str] = []
    if "name" in payload:
        saved_view.name = str(payload.get("name", "")).strip()
        if not saved_view.name:
            return _json_error("name is required", status=400)
        fields_to_update.append("name")

    if "client_safe" in payload:
        saved_view.client_safe = bool(payload.get("client_safe", False))
        fields_to_update.append("client_safe")

    if "filters" in payload:
        try:
            saved_view.filters = normalize_saved_view_filters(payload.get("filters"))
        except ValueError as exc:
            return _json_error(str(exc), status=400)
        fields_to_update.append("filters")

    if "sort" in payload:
        try:
            saved_view.sort = normalize_saved_view_sort(payload.get("sort"))
        except ValueError as exc:
            return _json_error(str(exc), status=400)
        fields_to_update.append("sort")

    if "group_by" in payload:
        try:
            saved_view.group_by = normalize_saved_view_group_by(payload.get("group_by"))
        except ValueError as exc:
            return _json_error(str(exc), status=400)
        fields_to_update.append("group_by")

    if fields_to_update:
        saved_view.save(update_fields=[*list(dict.fromkeys(fields_to_update)), "updated_at"])

    write_audit_event(
        org=org,
        actor_user=user,
        event_type="saved_view.updated",
        metadata={
            "saved_view_id": str(saved_view.id),
            "org_id": str(org.id),
            "project_id": str(saved_view.project_id),
            "owner_user_id": str(user.id),
            "updated_fields": list(dict.fromkeys(fields_to_update)),
        },
    )

    return JsonResponse({"saved_view": _saved_view_dict(saved_view)})


@require_http_methods(["GET", "POST"])
def custom_fields_collection_view(request: HttpRequest, org_id, project_id) -> JsonResponse:
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_org_read_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    project = Project.objects.filter(id=project_id, org_id=org.id).first()
    if project is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        fields = CustomFieldDefinition.objects.filter(
            org_id=org.id, project_id=project.id, archived_at__isnull=True
        ).order_by("created_at")
        if membership.role == OrgMembership.Role.CLIENT:
            fields = fields.filter(client_safe=True)
        return JsonResponse({"custom_fields": [_custom_field_def_dict(f) for f in fields]})

    membership = _require_org_pm_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    name = str(payload.get("name", "")).strip()
    field_type = str(payload.get("field_type", "")).strip()
    if not name:
        return _json_error("name is required", status=400)
    if field_type not in set(CustomFieldDefinition.FieldType.values):
        return _json_error("field_type is invalid", status=400)

    try:
        options = normalize_custom_field_options(field_type, payload.get("options"))
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    client_safe = bool(payload.get("client_safe", False))

    with transaction.atomic():
        try:
            field = CustomFieldDefinition.objects.create(
                org=org,
                project=project,
                name=name,
                field_type=field_type,
                options=options,
                client_safe=client_safe,
            )
        except IntegrityError:
            return _json_error("a custom field with this name already exists", status=400)

    write_audit_event(
        org=org,
        actor_user=user,
        event_type="custom_field.created",
        metadata={
            "custom_field_id": str(field.id),
            "org_id": str(org.id),
            "project_id": str(project.id),
            "field_type": field.field_type,
            "client_safe": bool(field.client_safe),
        },
    )

    return JsonResponse({"custom_field": _custom_field_def_dict(field)})


@require_http_methods(["PATCH", "DELETE"])
def custom_field_detail_view(request: HttpRequest, org_id, field_id) -> JsonResponse:
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_org_pm_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    field = (
        CustomFieldDefinition.objects.filter(id=field_id, org_id=org.id)
        .select_related("project")
        .first()
    )
    if field is None:
        return _json_error("not found", status=404)

    if request.method == "DELETE":
        if field.archived_at is None:
            field.archived_at = timezone.now()
            field.save(update_fields=["archived_at", "updated_at"])
            write_audit_event(
                org=org,
                actor_user=user,
                event_type="custom_field.archived",
                metadata={
                    "custom_field_id": str(field.id),
                    "org_id": str(org.id),
                    "project_id": str(field.project_id),
                },
            )
        return JsonResponse({}, status=204)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    fields_to_update: list[str] = []
    if "name" in payload:
        field.name = str(payload.get("name", "")).strip()
        if not field.name:
            return _json_error("name is required", status=400)
        fields_to_update.append("name")

    if "client_safe" in payload:
        field.client_safe = bool(payload.get("client_safe", False))
        fields_to_update.append("client_safe")

    if "options" in payload:
        try:
            field.options = normalize_custom_field_options(field.field_type, payload.get("options"))
        except ValueError as exc:
            return _json_error(str(exc), status=400)
        fields_to_update.append("options")

    if fields_to_update:
        with transaction.atomic():
            try:
                field.save(update_fields=[*list(dict.fromkeys(fields_to_update)), "updated_at"])
            except IntegrityError:
                return _json_error("a custom field with this name already exists", status=400)

    write_audit_event(
        org=org,
        actor_user=user,
        event_type="custom_field.updated",
        metadata={
            "custom_field_id": str(field.id),
            "org_id": str(org.id),
            "project_id": str(field.project_id),
            "updated_fields": list(dict.fromkeys(fields_to_update)),
        },
    )

    return JsonResponse({"custom_field": _custom_field_def_dict(field)})


def _patch_custom_field_values_for_work_item(
    *,
    org: Org,
    user,
    project: Project,
    work_item_type: str,
    work_item_id: uuid.UUID,
    values_payload: object,
) -> tuple[list[CustomFieldValue], JsonResponse | None]:
    if not isinstance(values_payload, dict):
        return [], _json_error("values must be an object", status=400)

    # Load allowed field definitions for this project once.
    defs = list(
        CustomFieldDefinition.objects.filter(
            org_id=org.id,
            project_id=project.id,
            archived_at__isnull=True,
        ).only("id", "field_type", "options")
    )
    defs_by_id = {str(d.id): d for d in defs}

    to_set: dict[uuid.UUID, object] = {}
    to_clear: set[uuid.UUID] = set()
    for field_id_raw, value in values_payload.items():
        try:
            field_uuid = uuid.UUID(str(field_id_raw))
        except (TypeError, ValueError):
            return [], _json_error("field ids must be UUIDs", status=400)

        definition = defs_by_id.get(str(field_uuid))
        if definition is None:
            return [], _json_error("invalid field_id for this project", status=400)

        if value is None:
            to_clear.add(field_uuid)
            continue

        try:
            normalized_value = validate_custom_field_value(
                definition.field_type, list(definition.options or []), value
            )
        except ValueError as exc:
            return [], _json_error(str(exc), status=400)

        to_set[field_uuid] = normalized_value

    if not to_set and not to_clear:
        return [], None

    updated_values: list[CustomFieldValue] = []
    with transaction.atomic():
        if to_clear:
            CustomFieldValue.objects.filter(
                org_id=org.id,
                project_id=project.id,
                work_item_type=work_item_type,
                work_item_id=work_item_id,
                field_id__in=to_clear,
            ).delete()

        for field_uuid, normalized_value in to_set.items():
            obj, _created = CustomFieldValue.objects.update_or_create(
                org_id=org.id,
                project_id=project.id,
                field_id=field_uuid,
                work_item_type=work_item_type,
                work_item_id=work_item_id,
                defaults={"value_json": normalized_value},
            )
            updated_values.append(obj)

    return updated_values, None


@require_http_methods(["PATCH"])
def task_custom_field_values_view(request: HttpRequest, org_id, task_id) -> JsonResponse:
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_org_pm_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    task = (
        Task.objects.filter(id=task_id, epic__project__org_id=org.id)
        .select_related("epic", "epic__project")
        .first()
    )
    if task is None:
        return _json_error("not found", status=404)

    project = task.epic.project

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    updated, err = _patch_custom_field_values_for_work_item(
        org=org,
        user=user,
        project=project,
        work_item_type=CustomFieldValue.WorkItemType.TASK,
        work_item_id=task.id,
        values_payload=payload.get("values"),
    )
    if err is not None:
        return err

    return JsonResponse({"custom_field_values": [_custom_field_value_dict(v) for v in updated]})


@require_http_methods(["PATCH"])
def subtask_custom_field_values_view(request: HttpRequest, org_id, subtask_id) -> JsonResponse:
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_org_pm_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    subtask = (
        Subtask.objects.filter(id=subtask_id, task__epic__project__org_id=org.id)
        .select_related("task", "task__epic", "task__epic__project")
        .first()
    )
    if subtask is None:
        return _json_error("not found", status=404)

    project = subtask.task.epic.project

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    updated, err = _patch_custom_field_values_for_work_item(
        org=org,
        user=user,
        project=project,
        work_item_type=CustomFieldValue.WorkItemType.SUBTASK,
        work_item_id=subtask.id,
        values_payload=payload.get("values"),
    )
    if err is not None:
        return err

    return JsonResponse({"custom_field_values": [_custom_field_value_dict(v) for v in updated]})
