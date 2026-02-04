from __future__ import annotations

import json
import uuid

from django.http import FileResponse, HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from audit.services import write_audit_event
from identity.models import Org, OrgMembership
from realtime.services import publish_org_event
from work_items.models import Epic, Task

from .models import Attachment, Comment
from .services import compute_sha256, render_markdown_to_safe_html


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


def _require_session_user(request: HttpRequest):
    if getattr(request, "api_key_principal", None) is not None:
        return None, _json_error("forbidden", status=403)
    if not request.user.is_authenticated:
        return None, _json_error("unauthorized", status=401)
    return request.user, None


def _require_org(org_id) -> Org | None:
    return Org.objects.filter(id=org_id).first()


def _require_collaboration_membership(user, org_id) -> OrgMembership | None:
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


def _user_ref(user) -> dict:
    return {"id": str(user.id), "display_name": getattr(user, "display_name", "")}


def _comment_dict(comment: Comment) -> dict:
    attachment_ids = [str(a.id) for a in getattr(comment, "attachments", []).all()]
    payload = {
        "id": str(comment.id),
        "created_at": comment.created_at.isoformat(),
        "author": _user_ref(comment.author_user),
        "body_markdown": comment.body_markdown,
        "body_html": comment.body_html,
    }
    if attachment_ids:
        payload["attachment_ids"] = attachment_ids
    return payload


def _attachment_download_url(*, org_id, attachment_id) -> str:
    return f"/api/orgs/{org_id}/attachments/{attachment_id}/download"


def _attachment_dict(attachment: Attachment) -> dict:
    return {
        "id": str(attachment.id),
        "created_at": attachment.created_at.isoformat(),
        "filename": attachment.original_filename,
        "content_type": attachment.content_type,
        "size_bytes": attachment.size_bytes,
        "sha256": attachment.sha256,
        "download_url": _attachment_download_url(
            org_id=attachment.org_id, attachment_id=attachment.id
        ),
        "comment_id": str(attachment.comment_id) if attachment.comment_id else None,
    }


def _require_task(org: Org, task_id) -> Task | None:
    return (
        Task.objects.select_related("epic__project")
        .filter(id=task_id, epic__project__org=org)
        .first()
    )


def _require_epic(org: Org, epic_id) -> Epic | None:
    return Epic.objects.select_related("project").filter(id=epic_id, project__org=org).first()


def _parse_optional_uuid(value: str) -> uuid.UUID | None:
    if value is None or not str(value).strip():
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        raise ValueError("must be a UUID") from None


@require_http_methods(["GET", "POST"])
def task_comments_collection_view(request: HttpRequest, org_id, task_id) -> JsonResponse:
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_collaboration_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    task = _require_task(org, task_id)
    if task is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        comments = (
            Comment.objects.filter(org=org, task=task)
            .select_related("author_user")
            .prefetch_related("attachments")
            .order_by("created_at", "id")
        )
        return JsonResponse({"comments": [_comment_dict(c) for c in comments]})

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    body_markdown = str(payload.get("body_markdown", "")).rstrip()
    if not body_markdown.strip():
        return _json_error("body_markdown is required", status=400)

    comment = Comment.objects.create(
        org=org,
        author_user=user,
        task=task,
        body_markdown=body_markdown,
        body_html=render_markdown_to_safe_html(body_markdown),
    )
    write_audit_event(
        org=org,
        actor_user=user,
        event_type="comment.created",
        metadata={"comment_id": str(comment.id), "task_id": str(task.id)},
    )
    publish_org_event(
        org_id=org.id,
        event_type="comment.created",
        data={
            "work_item_type": "task",
            "work_item_id": str(task.id),
            "comment_id": str(comment.id),
        },
    )
    return JsonResponse({"comment": _comment_dict(comment)}, status=201)


@require_http_methods(["GET", "POST"])
def epic_comments_collection_view(request: HttpRequest, org_id, epic_id) -> JsonResponse:
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_collaboration_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    epic = _require_epic(org, epic_id)
    if epic is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        comments = (
            Comment.objects.filter(org=org, epic=epic)
            .select_related("author_user")
            .prefetch_related("attachments")
            .order_by("created_at", "id")
        )
        return JsonResponse({"comments": [_comment_dict(c) for c in comments]})

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    body_markdown = str(payload.get("body_markdown", "")).rstrip()
    if not body_markdown.strip():
        return _json_error("body_markdown is required", status=400)

    comment = Comment.objects.create(
        org=org,
        author_user=user,
        epic=epic,
        body_markdown=body_markdown,
        body_html=render_markdown_to_safe_html(body_markdown),
    )
    write_audit_event(
        org=org,
        actor_user=user,
        event_type="comment.created",
        metadata={"comment_id": str(comment.id), "epic_id": str(epic.id)},
    )
    publish_org_event(
        org_id=org.id,
        event_type="comment.created",
        data={
            "work_item_type": "epic",
            "work_item_id": str(epic.id),
            "comment_id": str(comment.id),
        },
    )
    return JsonResponse({"comment": _comment_dict(comment)}, status=201)


@require_http_methods(["GET", "POST"])
def task_attachments_collection_view(request: HttpRequest, org_id, task_id) -> JsonResponse:
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_collaboration_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    task = _require_task(org, task_id)
    if task is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        attachments = (
            Attachment.objects.filter(org=org, task=task)
            .select_related("comment")
            .order_by("created_at", "id")
        )
        return JsonResponse({"attachments": [_attachment_dict(a) for a in attachments]})

    uploaded_file = request.FILES.get("file")
    if uploaded_file is None:
        return _json_error("file is required", status=400)

    comment_id_raw = request.POST.get("comment_id", "")
    try:
        comment_uuid = _parse_optional_uuid(comment_id_raw)
    except ValueError:
        return _json_error("comment_id must be a UUID", status=400)

    comment = None
    if comment_uuid is not None:
        comment = Comment.objects.filter(id=comment_uuid, org=org, task=task).first()
        if comment is None:
            return _json_error("invalid comment_id", status=400)

    attachment = Attachment(
        org=org,
        uploader_user=user,
        task=task,
        comment=comment,
        original_filename=str(getattr(uploaded_file, "name", "") or "upload.bin")[:255],
        content_type=str(getattr(uploaded_file, "content_type", "") or "")[:200],
        size_bytes=int(getattr(uploaded_file, "size", 0) or 0),
        sha256=compute_sha256(uploaded_file),
    )
    attachment.file = uploaded_file
    attachment.save()

    write_audit_event(
        org=org,
        actor_user=user,
        event_type="attachment.created",
        metadata={
            "attachment_id": str(attachment.id),
            "task_id": str(task.id),
            "comment_id": str(comment.id) if comment is not None else None,
            "sha256": attachment.sha256,
        },
    )

    return JsonResponse({"attachment": _attachment_dict(attachment)}, status=201)


@require_http_methods(["GET", "POST"])
def epic_attachments_collection_view(request: HttpRequest, org_id, epic_id) -> JsonResponse:
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_collaboration_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    epic = _require_epic(org, epic_id)
    if epic is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        attachments = (
            Attachment.objects.filter(org=org, epic=epic)
            .select_related("comment")
            .order_by("created_at", "id")
        )
        return JsonResponse({"attachments": [_attachment_dict(a) for a in attachments]})

    uploaded_file = request.FILES.get("file")
    if uploaded_file is None:
        return _json_error("file is required", status=400)

    comment_id_raw = request.POST.get("comment_id", "")
    try:
        comment_uuid = _parse_optional_uuid(comment_id_raw)
    except ValueError:
        return _json_error("comment_id must be a UUID", status=400)

    comment = None
    if comment_uuid is not None:
        comment = Comment.objects.filter(id=comment_uuid, org=org, epic=epic).first()
        if comment is None:
            return _json_error("invalid comment_id", status=400)

    attachment = Attachment(
        org=org,
        uploader_user=user,
        epic=epic,
        comment=comment,
        original_filename=str(getattr(uploaded_file, "name", "") or "upload.bin")[:255],
        content_type=str(getattr(uploaded_file, "content_type", "") or "")[:200],
        size_bytes=int(getattr(uploaded_file, "size", 0) or 0),
        sha256=compute_sha256(uploaded_file),
    )
    attachment.file = uploaded_file
    attachment.save()

    write_audit_event(
        org=org,
        actor_user=user,
        event_type="attachment.created",
        metadata={
            "attachment_id": str(attachment.id),
            "epic_id": str(epic.id),
            "comment_id": str(comment.id) if comment is not None else None,
            "sha256": attachment.sha256,
        },
    )

    return JsonResponse({"attachment": _attachment_dict(attachment)}, status=201)


@require_http_methods(["GET"])
def attachment_download_view(request: HttpRequest, org_id, attachment_id):
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_collaboration_membership(user, org.id)
    if membership is None:
        return _json_error("forbidden", status=403)

    attachment = (
        Attachment.objects.select_related("comment").filter(id=attachment_id, org=org).first()
    )
    if attachment is None:
        return _json_error("not found", status=404)

    response = FileResponse(
        attachment.file.open("rb"),
        as_attachment=True,
        filename=attachment.original_filename,
    )
    if attachment.content_type:
        response["Content-Type"] = attachment.content_type
    return response
