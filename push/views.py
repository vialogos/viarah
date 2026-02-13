from __future__ import annotations

import json
from typing import Any

from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from identity.models import OrgMembership
from notifications.models import NotificationChannel, NotificationEventType, NotificationPreference
from work_items.models import Project, ProjectMembership

from .models import PushSubscription
from .services import push_is_configured, vapid_public_key


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


def _subscription_dict(row: PushSubscription) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "endpoint": row.endpoint,
        "expiration_time": int(row.expiration_time) if row.expiration_time is not None else None,
        "user_agent": row.user_agent,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _initialize_default_push_prefs(*, user) -> None:
    """Initialize push preferences for key MVP events.

    This seeds defaults for projects the user can *actually access*:
    - org `admin`/`pm`: all projects in the org
    - org `member`/`client`: only projects where they have `ProjectMembership`

    Explicit user preferences are never overridden.
    """

    memberships = list(
        OrgMembership.objects.filter(user=user).values_list("org_id", "role")
    )
    if not memberships:
        return

    pm_org_ids = {
        org_id
        for org_id, role in memberships
        if role in {OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
    }
    restricted_org_ids = {
        org_id
        for org_id, role in memberships
        if role not in {OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
    }

    project_pairs: set[tuple[str, str]] = set()

    if pm_org_ids:
        for project_id, org_id in Project.objects.filter(org_id__in=pm_org_ids).values_list(
            "id", "org_id"
        ):
            project_pairs.add((str(project_id), str(org_id)))

    if restricted_org_ids:
        for project_id, org_id in ProjectMembership.objects.filter(
            user=user,
            project__org_id__in=restricted_org_ids,
        ).values_list("project_id", "project__org_id"):
            project_pairs.add((str(project_id), str(org_id)))

    if not project_pairs:
        return

    prefs: list[NotificationPreference] = []
    for project_id, org_id in sorted(project_pairs):
        for event_type in {
            NotificationEventType.COMMENT_CREATED,
            NotificationEventType.REPORT_PUBLISHED,
        }:
            prefs.append(
                NotificationPreference(
                    org_id=org_id,
                    project_id=project_id,
                    user_id=user.id,
                    event_type=event_type,
                    channel=NotificationChannel.PUSH,
                    enabled=True,
                )
            )

    if prefs:
        NotificationPreference.objects.bulk_create(prefs, ignore_conflicts=True)

@require_http_methods(["GET"])
def vapid_public_key_view(request: HttpRequest) -> JsonResponse:
    """Return the VAPID public key for web push.

    Auth: Session-only (see `docs/api/scope-map.yaml` operation `push__vapid_public_key_get`).
    Inputs: None.
    Returns: `{public_key}` (503 when push is not configured).
    Side effects: None.
    """
    _, err = _require_session_user(request)
    if err is not None:
        return err

    if not push_is_configured():
        return _json_error("push is not configured", status=503)

    key = vapid_public_key()
    if not key:
        return _json_error("push is not configured", status=503)

    return JsonResponse({"public_key": key})


@require_http_methods(["GET", "POST"])
def subscriptions_collection_view(request: HttpRequest) -> JsonResponse:
    """List or upsert push subscriptions for the current user.

    Auth: Session-only (see `docs/api/scope-map.yaml` operations `push__subscriptions_get` and
    `push__subscriptions_post`).
    Inputs: POST JSON supports a Web Push `subscription` object and optional `user_agent`.
    Returns: `{subscriptions: [...]}` for GET; `{subscription}` for POST.
    Side effects: POST upserts a `PushSubscription` and initializes default push preferences.
    """
    user, err = _require_session_user(request)
    if err is not None:
        return err

    if request.method == "GET":
        rows = PushSubscription.objects.filter(user=user).order_by("-created_at", "-id")
        return JsonResponse({"subscriptions": [_subscription_dict(r) for r in rows]})

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    raw_sub = payload.get("subscription")
    sub = raw_sub if isinstance(raw_sub, dict) else payload

    endpoint = str(sub.get("endpoint", "") or "").strip()
    keys = sub.get("keys")
    keys = keys if isinstance(keys, dict) else {}
    p256dh = str(keys.get("p256dh", "") or "").strip()
    auth = str(keys.get("auth", "") or "").strip()

    expiration_time = sub.get("expirationTime", None)
    if expiration_time is None:
        expiration_time = sub.get("expiration_time", None)
    try:
        expiration_value = int(expiration_time) if expiration_time is not None else None
    except (TypeError, ValueError):
        return _json_error("expirationTime must be a number or null", status=400)

    user_agent = str(payload.get("user_agent", "") or payload.get("userAgent", "") or "").strip()
    if not user_agent:
        user_agent = str(request.META.get("HTTP_USER_AGENT", "") or "").strip()

    if not endpoint:
        return _json_error("endpoint is required", status=400)
    if not p256dh:
        return _json_error("keys.p256dh is required", status=400)
    if not auth:
        return _json_error("keys.auth is required", status=400)

    with transaction.atomic():
        row, _created = PushSubscription.objects.update_or_create(
            user=user,
            endpoint=endpoint,
            defaults={
                "p256dh": p256dh,
                "auth": auth,
                "expiration_time": expiration_value,
                "user_agent": user_agent,
            },
        )
        _initialize_default_push_prefs(user=user)

    return JsonResponse({"subscription": _subscription_dict(row)}, status=201)


@require_http_methods(["DELETE"])
def subscription_detail_view(request: HttpRequest, subscription_id) -> HttpResponse:
    """Delete a push subscription for the current user.

    Auth: Session-only (see `docs/api/scope-map.yaml` operation `push__subscription_delete`).
    Inputs: Path `subscription_id`.
    Returns: 204 No Content.
    Side effects: Deletes the subscription row.
    """
    user, err = _require_session_user(request)
    if err is not None:
        return err

    row = PushSubscription.objects.filter(id=subscription_id, user=user).first()
    if row is None:
        return _json_error("not found", status=404)

    PushSubscription.objects.filter(id=row.id).delete()
    return HttpResponse(status=204)
