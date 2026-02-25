from __future__ import annotations

import hashlib
import json
import os
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from audit.services import write_audit_event
from identity.models import Org, OrgMembership
from realtime.services import publish_org_event
from work_items.models import Task

from .gitlab import GitLabClient, GitLabHttpError
from .models import GitLabWebhookDelivery, OrgGitLabIntegration, TaskGitLabLink
from .selectors import get_effective_gitlab_integration_for_org, get_global_gitlab_integration
from .services import (
    IntegrationConfigError,
    decrypt_token,
    encrypt_token,
    hash_webhook_secret,
    normalize_origin,
    parse_gitlab_web_url,
    webhook_secret_matches,
)
from .tasks import process_gitlab_webhook_delivery, refresh_gitlab_link_metadata


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


def _principal_project_id(principal) -> str | None:
    project_id = getattr(principal, "project_id", None)
    if project_id is None or str(project_id).strip() == "":
        return None
    return str(project_id).strip()


def _require_org_role(user, org: Org, *, roles: set[str]) -> OrgMembership | None:
    return (
        OrgMembership.objects.filter(user=user, org=org, role__in=roles)
        .select_related("org")
        .first()
    )


def _require_pm_admin_any_org(user) -> bool:
    return OrgMembership.objects.filter(
        user=user, role__in={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
    ).exists()


def _gitlab_integration_dict(integration) -> dict:
    if integration is None or not str(getattr(integration, "base_url", "") or "").strip():
        return {
            "base_url": None,
            "has_token": False,
            "token_set_at": None,
            "webhook_configured": False,
        }

    return {
        "base_url": str(getattr(integration, "base_url", "") or "").strip() or None,
        "has_token": bool(getattr(integration, "token_ciphertext", None)),
        "token_set_at": (
            getattr(integration, "token_set_at").isoformat()
            if getattr(integration, "token_set_at", None)
            else None
        ),
        "webhook_configured": bool(getattr(integration, "webhook_secret_hash", None)),
    }


def _gitlab_link_dict(link: TaskGitLabLink, *, now) -> dict:
    ttl_seconds = _gitlab_metadata_ttl_seconds()
    stale = link.last_synced_at is None or (now - link.last_synced_at).total_seconds() > ttl_seconds
    rate_limited = link.rate_limited_until is not None and link.rate_limited_until > now
    status = "ok"
    if link.last_synced_at is None:
        status = "never"
    elif stale:
        status = "stale"
    if link.last_sync_error_code:
        status = "error"

    return {
        "id": str(link.id),
        "url": link.web_url,
        "project_path": link.project_path,
        "gitlab_type": link.gitlab_type,
        "gitlab_iid": link.gitlab_iid,
        "cached_title": link.cached_title,
        "cached_state": link.cached_state,
        "cached_labels": list(link.cached_labels or []),
        "cached_assignees": list(link.cached_assignees or []),
        "last_synced_at": link.last_synced_at.isoformat() if link.last_synced_at else None,
        "sync": {
            "status": status,
            "stale": bool(stale),
            "rate_limited": bool(rate_limited),
            "rate_limited_until": (
                link.rate_limited_until.isoformat() if link.rate_limited_until else None
            ),
            "error_code": link.last_sync_error_code or None,
        },
    }


def _gitlab_metadata_ttl_seconds() -> int:
    ttl_raw = str(os.environ.get("GITLAB_METADATA_TTL_SECONDS", "3600")).strip()
    try:
        return max(int(ttl_raw), 1)
    except ValueError:
        return 3600


def _maybe_enqueue_refresh(link: TaskGitLabLink, *, now) -> None:
    ttl_seconds = _gitlab_metadata_ttl_seconds()
    stale = link.last_synced_at is None or (now - link.last_synced_at).total_seconds() > ttl_seconds
    if not stale:
        return
    if link.rate_limited_until and link.rate_limited_until > now:
        return

    min_interval = timedelta(seconds=15)
    if link.last_sync_attempt_at and link.last_sync_attempt_at + min_interval > now:
        return

    updated = TaskGitLabLink.objects.filter(
        id=link.id,
    ).update(last_sync_attempt_at=now, updated_at=now)
    if updated:
        refresh_gitlab_link_metadata.delay(str(link.id))


@require_http_methods(["GET", "PATCH"])
def settings_gitlab_integration_view(request: HttpRequest) -> JsonResponse:
    """Get or update instance-wide GitLab integration defaults (ADMIN/PM session-only)."""

    principal = _get_api_key_principal(request)
    if principal is not None:
        return _json_error("forbidden", status=403)

    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)
    if not _require_pm_admin_any_org(user):
        return _json_error("forbidden", status=403)

    integration = get_global_gitlab_integration()
    if request.method == "GET":
        return JsonResponse({"gitlab": _gitlab_integration_dict(integration)})

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    base_url_provided = "base_url" in payload
    base_url_raw = payload.get("base_url", None)
    token_raw = payload.get("token", None)
    webhook_secret_raw = payload.get("webhook_secret", None)

    normalized_base_url = None
    if base_url_provided:
        candidate = str(base_url_raw or "").strip()
        if not candidate:
            normalized_base_url = ""
        else:
            try:
                normalized_base_url = normalize_origin(candidate)
            except ValueError as exc:
                return _json_error(str(exc), status=400)

    base_url_next = integration.base_url
    if normalized_base_url is not None:
        base_url_next = normalized_base_url

    token_value = None
    if token_raw is not None:
        token_value = str(token_raw or "").strip()
        if token_value and not str(base_url_next or "").strip():
            return _json_error("base_url is required", status=400)

    secret_value = None
    if webhook_secret_raw is not None:
        secret_value = str(webhook_secret_raw or "").strip()
        if secret_value and not str(base_url_next or "").strip():
            return _json_error("base_url is required", status=400)

    now = timezone.now()

    if normalized_base_url is not None:
        integration.base_url = normalized_base_url
        if not normalized_base_url:
            integration.token_ciphertext = None
            integration.token_set_at = None
            integration.token_rotated_at = None
            integration.webhook_secret_hash = None

    if token_value is not None:
        if token_value:
            try:
                integration.token_ciphertext = encrypt_token(token_value)
            except IntegrationConfigError as exc:
                return _json_error(str(exc), status=400)
            if integration.token_set_at is None:
                integration.token_set_at = now
            integration.token_rotated_at = now
        else:
            integration.token_ciphertext = None
            integration.token_set_at = None
            integration.token_rotated_at = None

    if secret_value is not None:
        if secret_value:
            integration.webhook_secret_hash = hash_webhook_secret(secret_value)
        else:
            integration.webhook_secret_hash = None

    integration.save()
    return JsonResponse({"gitlab": _gitlab_integration_dict(integration)})


@require_http_methods(["GET", "PATCH", "DELETE"])
def org_gitlab_integration_view(request: HttpRequest, org_id) -> HttpResponse:
    """Get or update org-level GitLab integration settings.

    Auth: Session-only (ADMIN/PM) (see `docs/api/scope-map.yaml` operations
    `integrations__gitlab_integration_get` and `integrations__gitlab_integration_patch`).
    Inputs: Path `org_id`; PATCH JSON supports `{base_url?, token?, webhook_secret?}` (send empty
    strings to clear secrets).
    Returns: `{gitlab: {base_url, has_token, token_set_at, webhook_configured}}`.
    Side effects: Stores encrypted tokens and webhook secret hashes, and writes an audit event.
    """
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = get_object_or_404(Org, id=org_id)
    membership = _require_org_role(
        user, org, roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
    )
    if membership is None:
        return _json_error("forbidden", status=403)

    org_integration = OrgGitLabIntegration.objects.filter(org=org).first()

    if request.method == "GET":
        effective, source = get_effective_gitlab_integration_for_org(org_id=org.id)
        payload = _gitlab_integration_dict(effective)
        payload["source"] = source
        return JsonResponse({"gitlab": payload})

    if request.method == "DELETE":
        if org_integration is not None:
            OrgGitLabIntegration.objects.filter(id=org_integration.id).delete()
            write_audit_event(
                org=org,
                actor_user=user,
                event_type="integration.gitlab.deleted",
                metadata={
                    "org_id": str(org.id),
                },
            )
        return HttpResponse(status=204)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    base_url_raw = payload.get("base_url", None)
    token_raw = payload.get("token", None)
    webhook_secret_raw = payload.get("webhook_secret", None)

    try:
        normalized_base_url = (
            normalize_origin(str(base_url_raw)) if base_url_raw is not None else None
        )
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    now = timezone.now()

    if org_integration is None and normalized_base_url is None:
        return _json_error("base_url is required", status=400)

    if org_integration is None:
        org_integration = OrgGitLabIntegration(org=org, base_url=normalized_base_url or "")

    if normalized_base_url is not None:
        org_integration.base_url = normalized_base_url

    credential_updated = False
    webhook_updated = False

    if token_raw is not None:
        token_value = str(token_raw or "").strip()
        if token_value:
            try:
                org_integration.token_ciphertext = encrypt_token(token_value)
            except IntegrationConfigError as exc:
                return _json_error(str(exc), status=400)
            if org_integration.token_set_at is None:
                org_integration.token_set_at = now
            org_integration.token_rotated_at = now
            credential_updated = True
        else:
            org_integration.token_ciphertext = None
            org_integration.token_set_at = None
            org_integration.token_rotated_at = None
            credential_updated = True

    if webhook_secret_raw is not None:
        secret_value = str(webhook_secret_raw or "").strip()
        if secret_value:
            org_integration.webhook_secret_hash = hash_webhook_secret(secret_value)
            webhook_updated = True
        else:
            org_integration.webhook_secret_hash = None
            webhook_updated = True

    org_integration.save()

    write_audit_event(
        org=org,
        actor_user=user,
        event_type="integration.gitlab.updated",
        metadata={
            "org_id": str(org.id),
            "base_url": org_integration.base_url,
            "credential_updated": bool(credential_updated),
            "webhook_updated": bool(webhook_updated),
        },
    )

    payload = _gitlab_integration_dict(org_integration)
    payload["source"] = "org"
    return JsonResponse({"gitlab": payload})


@require_http_methods(["POST"])
def gitlab_integration_validate_view(request: HttpRequest, org_id) -> JsonResponse:
    """Validate the stored org GitLab token by calling `/api/v4/user`.

    Auth: Session-only (ADMIN/PM).
    Returns: `{status: "valid"|"invalid"|"not_validated", error_code: string|null}`.
    """
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    org = get_object_or_404(Org, id=org_id)
    membership = _require_org_role(
        user, org, roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
    )
    if membership is None:
        return _json_error("forbidden", status=403)

    integration, _source = get_effective_gitlab_integration_for_org(org_id=org.id)
    if integration is None:
        return JsonResponse({"status": "not_validated", "error_code": "missing_integration"})
    if not integration.token_ciphertext:
        return JsonResponse({"status": "not_validated", "error_code": "missing_token"})

    try:
        token = decrypt_token(integration.token_ciphertext)
    except IntegrationConfigError as exc:
        message = str(exc)
        code = "encryption_key_missing"
        if "ciphertext" in message:
            code = "invalid_token_ciphertext"
        elif "invalid" in message:
            code = "encryption_key_invalid"
        return JsonResponse({"status": "not_validated", "error_code": code})

    client = GitLabClient(base_url=integration.base_url, token=token)
    try:
        client.get_user()
    except GitLabHttpError as exc:
        if exc.status_code == 429:
            return JsonResponse({"status": "not_validated", "error_code": "rate_limited"})
        if exc.status_code in {401, 403}:
            return JsonResponse({"status": "invalid", "error_code": "auth_error"})
        if exc.status_code == 0:
            return JsonResponse({"status": "not_validated", "error_code": "network_error"})
        return JsonResponse({"status": "not_validated", "error_code": f"http_{exc.status_code}"})

    return JsonResponse({"status": "valid", "error_code": None})


@require_http_methods(["GET", "POST"])
def task_gitlab_links_collection_view(request: HttpRequest, org_id, task_id) -> JsonResponse:
    """List or create GitLab links attached to a task.

    Auth: Session or API key (see `docs/api/scope-map.yaml` operations
    `integrations__task_gitlab_links_get` and `integrations__task_gitlab_links_post`).
    Inputs: Path `org_id`, `task_id`; POST JSON `{url}` (GitLab web URL).
    Returns: `{links: [...]}` for GET; `{link}` for POST (includes cached metadata + sync status).
    Side effects: GET may enqueue metadata refresh tasks.
    POST creates a link and enqueues a refresh.
    """
    required_scope = "read" if request.method == "GET" else "write"
    org = get_object_or_404(Org, id=org_id)
    principal = _get_api_key_principal(request)
    if principal is not None:
        if str(org.id) != str(getattr(principal, "org_id", "")):
            return _json_error("forbidden", status=403)
        if not _principal_has_scope(principal, required_scope):
            return _json_error("forbidden", status=403)
    else:
        user = _require_authenticated_user(request)
        if user is None:
            return _json_error("unauthorized", status=401)
        membership = _require_org_role(
            user,
            org,
            roles={
                OrgMembership.Role.ADMIN,
                OrgMembership.Role.PM,
                OrgMembership.Role.MEMBER,
            },
        )
        if membership is None:
            return _json_error("forbidden", status=403)

    task = get_object_or_404(Task.objects.select_related("epic__project"), id=task_id)
    if str(task.epic.project.org_id) != str(org.id):
        return _json_error("not found", status=404)
    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None and str(task.epic.project_id) != project_id_restriction:
            return _json_error("not found", status=404)

    if request.method == "GET":
        now = timezone.now()
        links = list(TaskGitLabLink.objects.filter(task=task).order_by("created_at"))
        for link in links:
            _maybe_enqueue_refresh(link, now=now)
        return JsonResponse({"links": [_gitlab_link_dict(link, now=now) for link in links]})

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    url = str(payload.get("url", "")).strip()
    if not url:
        return _json_error("url is required", status=400)

    try:
        parsed = parse_gitlab_web_url(url)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    integration, _integration_source = get_effective_gitlab_integration_for_org(org_id=org.id)
    if integration is None:
        if principal is None:
            return _json_error("gitlab integration is not configured", status=400)
        integration = OrgGitLabIntegration.objects.create(
            org=org,
            base_url=normalize_origin(parsed.origin),
        )

    if normalize_origin(integration.base_url) != normalize_origin(parsed.origin):
        return _json_error("url host does not match configured gitlab base_url", status=400)

    link = TaskGitLabLink(
        task=task,
        web_url=parsed.canonical_web_url,
        project_path=parsed.project_path,
        gitlab_type=parsed.gitlab_type,
        gitlab_iid=parsed.gitlab_iid,
    )

    try:
        with transaction.atomic():
            link.save()
    except IntegrityError:
        return _json_error("duplicate link for task", status=400)

    refresh_gitlab_link_metadata.delay(str(link.id))
    publish_org_event(
        org_id=org.id,
        event_type="gitlab_link.updated",
        data={
            "project_id": str(task.epic.project_id),
            "task_id": str(task.id),
            "link_id": str(link.id),
            "gitlab_type": str(link.gitlab_type),
            "gitlab_iid": int(link.gitlab_iid),
            "reason": "created",
        },
    )
    now = timezone.now()
    return JsonResponse({"link": _gitlab_link_dict(link, now=now)})


@require_http_methods(["DELETE"])
def task_gitlab_link_delete_view(request: HttpRequest, org_id, task_id, link_id) -> HttpResponse:
    """Delete a GitLab link from a task.

    Auth: Session or API key (see `docs/api/scope-map.yaml` operation
    `integrations__task_gitlab_link_delete`).
    Inputs: Path `org_id`, `task_id`, `link_id`.
    Returns: 204 No Content.
    Side effects: Deletes the `TaskGitLabLink` row.
    """
    org = get_object_or_404(Org, id=org_id)
    principal = _get_api_key_principal(request)
    if principal is not None:
        if str(org.id) != str(getattr(principal, "org_id", "")):
            return _json_error("forbidden", status=403)
        if not _principal_has_scope(principal, "write"):
            return _json_error("forbidden", status=403)
    else:
        user = _require_authenticated_user(request)
        if user is None:
            return _json_error("unauthorized", status=401)
        membership = _require_org_role(
            user,
            org,
            roles={
                OrgMembership.Role.ADMIN,
                OrgMembership.Role.PM,
                OrgMembership.Role.MEMBER,
            },
        )
        if membership is None:
            return _json_error("forbidden", status=403)

    task = get_object_or_404(Task.objects.select_related("epic__project"), id=task_id)
    if str(task.epic.project.org_id) != str(org.id):
        return _json_error("not found", status=404)
    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None and str(task.epic.project_id) != project_id_restriction:
            return _json_error("not found", status=404)

    link = TaskGitLabLink.objects.filter(id=link_id, task=task).first()
    if link is None:
        return _json_error("not found", status=404)

    TaskGitLabLink.objects.filter(id=link.id, task=task).delete()
    publish_org_event(
        org_id=org.id,
        event_type="gitlab_link.updated",
        data={
            "project_id": str(task.epic.project_id),
            "task_id": str(task.id),
            "link_id": str(link.id),
            "gitlab_type": str(link.gitlab_type),
            "gitlab_iid": int(link.gitlab_iid),
            "reason": "deleted",
        },
    )

    return HttpResponse(status=204)


@csrf_exempt
@require_http_methods(["POST"])
def gitlab_webhook_view(request: HttpRequest, org_id) -> JsonResponse:
    """Receive and queue a GitLab webhook delivery for async processing.

    Auth: `X-Gitlab-Token` header must match the configured org webhook secret (see
    `docs/api/scope-map.yaml` operation `integrations__gitlab_webhook_post`).
    Inputs: Raw JSON body; GitLab headers such as `X-Gitlab-Event` and `X-Gitlab-Event-UUID`.
    Returns: `{status: accepted}`.
    When the delivery has already been seen, returns `{status: duplicate}`.
    Side effects: Creates a `GitLabWebhookDelivery` record and enqueues a Celery processing task.
    """
    org = get_object_or_404(Org, id=org_id)
    integration = OrgGitLabIntegration.objects.filter(org=org).first()
    if integration is None or not integration.webhook_secret_hash:
        global_integration = get_global_gitlab_integration()
        if global_integration.webhook_secret_hash:
            integration = global_integration
        else:
            return _json_error("not found", status=404)

    provided = request.META.get("HTTP_X_GITLAB_TOKEN", "")
    if not provided or not webhook_secret_matches(
        expected_hash=integration.webhook_secret_hash, provided_secret=provided
    ):
        return _json_error("forbidden", status=403)

    raw_body = request.body or b""
    payload_hash = hashlib.sha256(raw_body).hexdigest()

    event_uuid = str(request.META.get("HTTP_X_GITLAB_EVENT_UUID", "")).strip() or None
    event_type = str(request.META.get("HTTP_X_GITLAB_EVENT", "")).strip()

    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return _json_error("invalid JSON", status=400)

    project_path = ""
    gitlab_type = ""
    gitlab_iid = None

    if isinstance(payload, dict):
        project = payload.get("project")
        if isinstance(project, dict):
            project_path = str(project.get("path_with_namespace", "")).strip()

        object_attributes = payload.get("object_attributes")
        if isinstance(object_attributes, dict):
            iid_raw = object_attributes.get("iid")
            try:
                gitlab_iid = int(iid_raw)
            except (TypeError, ValueError):
                gitlab_iid = None

    if event_type == "Issue Hook":
        gitlab_type = TaskGitLabLink.GitLabType.ISSUE
    elif event_type == "Merge Request Hook":
        gitlab_type = TaskGitLabLink.GitLabType.MERGE_REQUEST

    delivery = GitLabWebhookDelivery(
        org=org,
        event_uuid=event_uuid,
        event_type=event_type,
        project_path=project_path,
        gitlab_type=gitlab_type,
        gitlab_iid=gitlab_iid,
        payload_sha256=payload_hash,
    )
    try:
        with transaction.atomic():
            delivery.save()
    except IntegrityError:
        return JsonResponse({"status": "duplicate"}, status=202)

    process_gitlab_webhook_delivery.delay(str(delivery.id))
    return JsonResponse({"status": "accepted"}, status=202)
