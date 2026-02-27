from __future__ import annotations

import json
import uuid

from django.http import FileResponse, HttpRequest, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from api_keys.middleware import ApiKeyPrincipal
from audit.services import write_audit_event
from identity.models import Org, OrgMembership
from identity.rbac import platform_org_role
from notifications.models import NotificationEventType
from notifications.services import emit_project_event
from realtime.services import publish_org_event
from work_items.models import Epic, ProjectMembership, Task

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
    if not request.user.is_authenticated:
        return None, _json_error("unauthorized", status=401)
    return request.user, None


def _get_api_key_principal(request: HttpRequest) -> ApiKeyPrincipal | None:
    principal = getattr(request, "api_key_principal", None)
    if principal is None:
        return None
    if not isinstance(principal, ApiKeyPrincipal):
        return None
    return principal


def _principal_has_scope(principal: ApiKeyPrincipal, required: str) -> bool:
    scopes = set(getattr(principal, "scopes", None) or [])
    if required == "read":
        return "read" in scopes or "write" in scopes
    return required in scopes


def _principal_project_id(principal: ApiKeyPrincipal) -> uuid.UUID | None:
    project_id = getattr(principal, "project_id", None)
    if project_id is None or str(project_id).strip() == "":
        return None
    try:
        return uuid.UUID(str(project_id))
    except (TypeError, ValueError):
        return None


def _api_key_actor_user(request: HttpRequest):
    api_key = getattr(request, "api_key", None)
    return getattr(api_key, "created_by_user", None)


def _require_org(org_id) -> Org | None:
    return Org.objects.filter(id=org_id).first()


def _require_collaboration_membership(user, org_id) -> OrgMembership | None:
    platform_role = platform_org_role(user)
    if platform_role in {OrgMembership.Role.ADMIN, OrgMembership.Role.PM}:
        return OrgMembership(org_id=org_id, user=user, role=platform_role)

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


def _require_collaboration_read_membership(user, org_id) -> OrgMembership | None:
    platform_role = platform_org_role(user)
    if platform_role in {OrgMembership.Role.ADMIN, OrgMembership.Role.PM}:
        return OrgMembership(org_id=org_id, user=user, role=platform_role)

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


def _session_requires_project_membership(membership: OrgMembership | None) -> bool:
    return membership is not None and membership.role in {
        OrgMembership.Role.MEMBER,
        OrgMembership.Role.CLIENT,
    }


def _require_project_membership(
    membership: OrgMembership | None, *, project_id: uuid.UUID
) -> JsonResponse | None:
    """Enforce project membership for session MEMBER/CLIENT users."""

    if not _session_requires_project_membership(membership):
        return None

    assert membership is not None

    if not ProjectMembership.objects.filter(
        project_id=project_id,
        user_id=membership.user_id,
    ).exists():
        return _json_error("not found", status=404)

    return None


def _comment_dict(comment: Comment, *, include_attachments: bool) -> dict:
    payload = {
        "id": str(comment.id),
        "created_at": comment.created_at.isoformat(),
        "author": _user_ref(comment.author_user),
        "body_markdown": comment.body_markdown,
        "body_html": comment.body_html,
        "client_safe": bool(comment.client_safe),
    }
    if include_attachments:
        attachment_ids = [str(a.id) for a in getattr(comment, "attachments", []).all()]
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


def _resolve_comment_create_overrides(
    *,
    org: Org,
    principal: ApiKeyPrincipal | None,
    payload: dict,
    default_author_user,
) -> tuple[object | None, object | None, JsonResponse | None]:
    """Resolve optional comment overrides used by CLI imports.

    `author_user_id` and `created_at` are only accepted for API keys, and only when the API key's
    creator is an ADMIN/PM in the org. Session callers cannot set these to avoid impersonation.
    """
    author_user_id_raw = payload.get("author_user_id")
    created_at_raw = payload.get("created_at")

    if principal is None:
        if author_user_id_raw is not None:
            return None, None, _json_error("author_user_id is not allowed", status=400)
        if created_at_raw is not None:
            return None, None, _json_error("created_at is not allowed", status=400)
        return default_author_user, None, None

    has_author_override = author_user_id_raw is not None and str(author_user_id_raw).strip()
    has_created_at_override = created_at_raw is not None and str(created_at_raw).strip()
    if not has_author_override and not has_created_at_override:
        return default_author_user, None, None

    actor_user = default_author_user
    if actor_user is None:
        return None, None, _json_error("forbidden", status=403)

    actor_membership = OrgMembership.objects.filter(
        org=org,
        user=actor_user,
        role__in={OrgMembership.Role.ADMIN, OrgMembership.Role.PM},
    ).first()
    if actor_membership is None:
        return None, None, _json_error("forbidden", status=403)

    author_user = default_author_user
    if has_author_override:
        try:
            author_user_id = uuid.UUID(str(author_user_id_raw))
        except (TypeError, ValueError):
            return None, None, _json_error("author_user_id must be a UUID", status=400)

        membership = (
            OrgMembership.objects.filter(org=org, user_id=author_user_id)
            .select_related("user")
            .first()
        )
        if membership is None:
            return None, None, _json_error("invalid author_user_id", status=400)
        author_user = membership.user

    created_at_override = None
    if has_created_at_override:
        parsed = parse_datetime(str(created_at_raw))
        if parsed is None:
            return (
                None,
                None,
                _json_error("created_at must be an ISO-8601 datetime string", status=400),
            )
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        created_at_override = parsed

    return author_user, created_at_override, None


@require_http_methods(["GET", "POST"])
def task_comments_collection_view(request: HttpRequest, org_id, task_id) -> JsonResponse:
    """List or create comments for a task.

    Auth: Session (org member) or API key (see `docs/api/scope-map.yaml` operations
    `collaboration__task_comments_get` and `collaboration__task_comments_post`).
    CLIENT access is limited to client-safe tasks and comments.
    Inputs: Path `org_id`, `task_id`; POST JSON
    `{body_markdown, client_safe?, author_user_id?, created_at?}`.
    Returns: `{comments: [...]}` for GET; `{comment}` for POST.
    Side effects: POST writes an audit event and emits realtime/notification events.
    """
    principal = _get_api_key_principal(request)
    user = None
    membership = None
    if principal is None:
        user, err = _require_session_user(request)
        if err is not None:
            return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    required_scope = "read" if request.method == "GET" else "write"
    if principal is not None:
        if str(org.id) != str(principal.org_id):
            return _json_error("forbidden", status=403)
        if not _principal_has_scope(principal, required_scope):
            return _json_error("forbidden", status=403)
    else:
        membership = _require_collaboration_read_membership(user, org.id)
        if membership is None:
            return _json_error("forbidden", status=403)

    task = _require_task(org, task_id)
    if task is None:
        return _json_error("not found", status=404)

    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None and str(project_id_restriction) != str(
            task.epic.project_id
        ):
            return _json_error("not found", status=404)
        client_safe_only = False
    else:
        membership_err = _require_project_membership(membership, project_id=task.epic.project_id)
        if membership_err is not None:
            return membership_err

        client_safe_only = membership.role == OrgMembership.Role.CLIENT
    if client_safe_only and not task.client_safe:
        return _json_error("not found", status=404)

    if request.method == "GET":
        comments = (
            Comment.objects.filter(org=org, task=task)
            .select_related("author_user")
            .prefetch_related("attachments")
            .order_by("created_at", "id")
        )
        if client_safe_only:
            comments = comments.filter(client_safe=True)
        comment_payloads = [
            _comment_dict(c, include_attachments=not client_safe_only) for c in comments
        ]
        return JsonResponse({"comments": comment_payloads})

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    body_markdown = str(payload.get("body_markdown", "")).rstrip()
    if not body_markdown.strip():
        return _json_error("body_markdown is required", status=400)

    if principal is not None:
        user = _api_key_actor_user(request)
        if user is None:
            return _json_error("forbidden", status=403)

    comment_client_safe = True if client_safe_only else bool(payload.get("client_safe", False))
    author_user, created_at_override, err = _resolve_comment_create_overrides(
        org=org,
        principal=principal,
        payload=payload,
        default_author_user=user,
    )
    if err is not None:
        return err

    comment = Comment.objects.create(
        org=org,
        author_user=author_user,
        task=task,
        body_markdown=body_markdown,
        body_html=render_markdown_to_safe_html(body_markdown),
        client_safe=comment_client_safe,
    )
    if created_at_override is not None:
        comment.created_at = created_at_override
        comment.save(update_fields=["created_at"])
    write_audit_event(
        org=org,
        actor_user=author_user,
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

    emit_project_event(
        org=org,
        project=task.epic.project,
        event_type=NotificationEventType.COMMENT_CREATED,
        actor_user=author_user,
        data={
            "work_item_type": "task",
            "work_item_id": str(task.id),
            "work_item_title": task.title,
            "project_id": str(task.epic.project_id),
            "project_name": task.epic.project.name,
            "epic_id": str(task.epic_id),
            "epic_title": getattr(task.epic, "title", "") or "",
            "comment_id": str(comment.id),
        },
        client_visible=bool(task.client_safe and comment.client_safe),
    )
    return JsonResponse(
        {"comment": _comment_dict(comment, include_attachments=not client_safe_only)}, status=201
    )


@require_http_methods(["GET", "POST"])
def epic_comments_collection_view(request: HttpRequest, org_id, epic_id) -> JsonResponse:
    """List or create comments for an epic.

    Auth: Session (org member) or API key (see `docs/api/scope-map.yaml` operations
    `collaboration__epic_comments_get` and `collaboration__epic_comments_post`).
    Inputs: Path `org_id`, `epic_id`; POST JSON `{body_markdown, author_user_id?, created_at?}`.
    Returns: `{comments: [...]}` for GET; `{comment}` for POST.
    Side effects: POST writes an audit event and emits realtime/notification events.
    """
    principal = _get_api_key_principal(request)
    user = None
    membership = None
    if principal is None:
        user, err = _require_session_user(request)
        if err is not None:
            return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    required_scope = "read" if request.method == "GET" else "write"
    if principal is not None:
        if str(org.id) != str(principal.org_id):
            return _json_error("forbidden", status=403)
        if not _principal_has_scope(principal, required_scope):
            return _json_error("forbidden", status=403)
    else:
        membership = _require_collaboration_membership(user, org.id)
        if membership is None:
            return _json_error("forbidden", status=403)

    epic = _require_epic(org, epic_id)
    if epic is None:
        return _json_error("not found", status=404)

    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None and str(project_id_restriction) != str(
            epic.project_id
        ):
            return _json_error("not found", status=404)
    else:
        membership_err = _require_project_membership(membership, project_id=epic.project_id)
        if membership_err is not None:
            return membership_err

    if request.method == "GET":
        comments = (
            Comment.objects.filter(org=org, epic=epic)
            .select_related("author_user")
            .prefetch_related("attachments")
            .order_by("created_at", "id")
        )
        comment_payloads = [_comment_dict(c, include_attachments=True) for c in comments]
        return JsonResponse({"comments": comment_payloads})

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    body_markdown = str(payload.get("body_markdown", "")).rstrip()
    if not body_markdown.strip():
        return _json_error("body_markdown is required", status=400)

    if principal is not None:
        user = _api_key_actor_user(request)
        if user is None:
            return _json_error("forbidden", status=403)

    author_user, created_at_override, err = _resolve_comment_create_overrides(
        org=org,
        principal=principal,
        payload=payload,
        default_author_user=user,
    )
    if err is not None:
        return err

    comment = Comment.objects.create(
        org=org,
        author_user=author_user,
        epic=epic,
        body_markdown=body_markdown,
        body_html=render_markdown_to_safe_html(body_markdown),
    )
    if created_at_override is not None:
        comment.created_at = created_at_override
        comment.save(update_fields=["created_at"])
    write_audit_event(
        org=org,
        actor_user=author_user,
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

    emit_project_event(
        org=org,
        project=epic.project,
        event_type=NotificationEventType.COMMENT_CREATED,
        actor_user=author_user,
        data={
            "work_item_type": "epic",
            "work_item_id": str(epic.id),
            "work_item_title": epic.title,
            "project_id": str(epic.project_id),
            "project_name": epic.project.name,
            "comment_id": str(comment.id),
        },
        client_visible=False,
    )
    return JsonResponse({"comment": _comment_dict(comment, include_attachments=True)}, status=201)


@require_http_methods(["GET", "POST"])
def task_attachments_collection_view(request: HttpRequest, org_id, task_id) -> JsonResponse:
    """List or upload attachments for a task.

    Auth: Session-only (see `docs/api/scope-map.yaml` operations
    `collaboration__task_attachments_get` and `collaboration__task_attachments_post`).
    Inputs: Path `org_id`, `task_id`; POST multipart form with `file` and optional `comment_id`.
    Returns: `{attachments: [...]}` for GET; `{attachment}` for POST.
    Side effects: POST stores a file, creates an attachment record, and writes an audit event.
    """
    principal = _get_api_key_principal(request)
    user = None
    membership = None
    if principal is None:
        user, err = _require_session_user(request)
        if err is not None:
            return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    required_scope = "read" if request.method == "GET" else "write"
    if principal is not None:
        if str(org.id) != str(principal.org_id):
            return _json_error("forbidden", status=403)
        if not _principal_has_scope(principal, required_scope):
            return _json_error("forbidden", status=403)
    else:
        membership = _require_collaboration_membership(user, org.id)
        if membership is None:
            return _json_error("forbidden", status=403)

    task = _require_task(org, task_id)
    if task is None:
        return _json_error("not found", status=404)
    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None and str(project_id_restriction) != str(
            task.epic.project_id
        ):
            return _json_error("not found", status=404)

    membership_err = _require_project_membership(membership, project_id=task.epic.project_id)
    if membership_err is not None:
        return membership_err

    if request.method == "GET":
        attachments = (
            Attachment.objects.filter(org=org, task=task)
            .select_related("comment")
            .order_by("created_at", "id")
        )
        return JsonResponse({"attachments": [_attachment_dict(a) for a in attachments]})

    if principal is not None:
        user = _api_key_actor_user(request)
        if user is None:
            return _json_error("forbidden", status=403)

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
    """List or upload attachments for an epic.

    Auth: Session-only (see `docs/api/scope-map.yaml` operations
    `collaboration__epic_attachments_get` and `collaboration__epic_attachments_post`).
    Inputs: Path `org_id`, `epic_id`; POST multipart form with `file` and optional `comment_id`.
    Returns: `{attachments: [...]}` for GET; `{attachment}` for POST.
    Side effects: POST stores a file, creates an attachment record, and writes an audit event.
    """
    principal = _get_api_key_principal(request)
    user = None
    if principal is None:
        user, err = _require_session_user(request)
        if err is not None:
            return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    required_scope = "read" if request.method == "GET" else "write"
    if principal is not None:
        if str(org.id) != str(principal.org_id):
            return _json_error("forbidden", status=403)
        if not _principal_has_scope(principal, required_scope):
            return _json_error("forbidden", status=403)
    else:
        membership = _require_collaboration_membership(user, org.id)
        if membership is None:
            return _json_error("forbidden", status=403)

    epic = _require_epic(org, epic_id)
    if epic is None:
        return _json_error("not found", status=404)
    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None and str(project_id_restriction) != str(
            epic.project_id
        ):
            return _json_error("not found", status=404)

    membership_err = _require_project_membership(membership, project_id=epic.project_id)
    if membership_err is not None:
        return membership_err

    if request.method == "GET":
        attachments = (
            Attachment.objects.filter(org=org, epic=epic)
            .select_related("comment")
            .order_by("created_at", "id")
        )
        return JsonResponse({"attachments": [_attachment_dict(a) for a in attachments]})

    if principal is not None:
        user = _api_key_actor_user(request)
        if user is None:
            return _json_error("forbidden", status=403)

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
    """Download an attachment file.

    Auth: Session-only (see `docs/api/scope-map.yaml` operation
    `collaboration__attachment_download_get`).
    Inputs: Path `org_id`, `attachment_id`.
    Returns: File response with `Content-Type` when available.
    Side effects: None.
    """
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
        Attachment.objects.select_related(
            "comment",
            "task__epic__project",
            "epic__project",
        )
        .filter(id=attachment_id, org=org)
        .first()
    )
    if attachment is None:
        return _json_error("not found", status=404)

    project_id = None
    if attachment.task_id and attachment.task is not None:
        project_id = attachment.task.epic.project_id
    elif attachment.epic_id and attachment.epic is not None:
        project_id = attachment.epic.project_id

    if project_id is not None:
        membership_err = _require_project_membership(membership, project_id=project_id)
        if membership_err is not None:
            return membership_err

    response = FileResponse(
        attachment.file.open("rb"),
        as_attachment=True,
        filename=attachment.original_filename,
    )
    if attachment.content_type:
        response["Content-Type"] = attachment.content_type
    return response
