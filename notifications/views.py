from __future__ import annotations

import json
import uuid

from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from identity.models import Org, OrgMembership
from work_items.models import Project

from .models import (
    EmailDeliveryLog,
    InAppNotification,
    NotificationChannel,
    NotificationEventType,
    NotificationPreference,
    ProjectNotificationSetting,
)
from .services import MAX_IN_APP_QUERY_LIMIT, effective_preference_for_membership


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


def _require_membership(user, org: Org, *, allowed_roles: set[str]) -> OrgMembership | None:
    return (
        OrgMembership.objects.filter(user=user, org=org, role__in=allowed_roles)
        .select_related("org")
        .first()
    )


def _require_project(org: Org, project_id) -> Project | None:
    return Project.objects.filter(id=project_id, org=org).first()


def _in_app_dict(row: InAppNotification) -> dict:
    event = getattr(row, "event", None)
    return {
        "id": str(row.id),
        "event_id": str(row.event_id),
        "org_id": str(row.org_id),
        "project_id": str(row.project_id) if row.project_id else None,
        "event_type": getattr(event, "event_type", ""),
        "data": getattr(event, "data_json", {}) if event is not None else {},
        "read_at": row.read_at.isoformat() if row.read_at else None,
        "created_at": row.created_at.isoformat(),
    }


def _delivery_log_dict(row: EmailDeliveryLog) -> dict:
    return {
        "id": str(row.id),
        "org_id": str(row.org_id),
        "project_id": str(row.project_id) if row.project_id else None,
        "notification_event_id": str(row.notification_event_id)
        if row.notification_event_id
        else None,
        "outbound_draft_id": str(row.outbound_draft_id) if row.outbound_draft_id else None,
        "recipient_user_id": str(row.recipient_user_id) if row.recipient_user_id else None,
        "to_email": row.to_email,
        "subject": row.subject,
        "status": row.status,
        "attempt_number": int(row.attempt_number),
        "error_code": row.error_code,
        "error_detail": row.error_detail,
        "queued_at": row.queued_at.isoformat() if row.queued_at else None,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _normalize_limit(value: object) -> int:
    try:
        limit = int(str(value or "").strip() or "50")
    except ValueError:
        raise ValueError("limit must be an integer") from None

    return max(1, min(limit, MAX_IN_APP_QUERY_LIMIT))


@require_http_methods(["GET"])
def my_notifications_collection_view(request: HttpRequest, org_id) -> JsonResponse:
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_membership(
        user,
        org,
        allowed_roles={
            OrgMembership.Role.ADMIN,
            OrgMembership.Role.PM,
            OrgMembership.Role.MEMBER,
            OrgMembership.Role.CLIENT,
        },
    )
    if membership is None:
        return _json_error("forbidden", status=403)

    project_id_raw = request.GET.get("project_id")
    project_id = None
    if project_id_raw is not None and str(project_id_raw).strip():
        try:
            project_id = uuid.UUID(str(project_id_raw))
        except (TypeError, ValueError):
            return _json_error("project_id must be a UUID", status=400)

    unread_only_raw = str(request.GET.get("unread_only", "")).strip().lower()
    unread_only = unread_only_raw in {"1", "true", "yes", "on"}

    try:
        limit = _normalize_limit(request.GET.get("limit"))
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    qs = (
        InAppNotification.objects.filter(org=org, recipient_user=user)
        .select_related("event")
        .order_by("-created_at", "-id")
    )
    if project_id is not None:
        qs = qs.filter(project_id=project_id)
    if unread_only:
        qs = qs.filter(read_at__isnull=True)
    rows = list(qs[:limit])
    return JsonResponse({"notifications": [_in_app_dict(n) for n in rows]})


@require_http_methods(["GET"])
def my_notifications_badge_view(request: HttpRequest, org_id) -> JsonResponse:
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_membership(
        user,
        org,
        allowed_roles={
            OrgMembership.Role.ADMIN,
            OrgMembership.Role.PM,
            OrgMembership.Role.MEMBER,
            OrgMembership.Role.CLIENT,
        },
    )
    if membership is None:
        return _json_error("forbidden", status=403)

    project_id_raw = request.GET.get("project_id")
    project_id = None
    if project_id_raw is not None and str(project_id_raw).strip():
        try:
            project_id = uuid.UUID(str(project_id_raw))
        except (TypeError, ValueError):
            return _json_error("project_id must be a UUID", status=400)

    qs = InAppNotification.objects.filter(org=org, recipient_user=user, read_at__isnull=True)
    if project_id is not None:
        qs = qs.filter(project_id=project_id)

    return JsonResponse({"unread_count": qs.count()})


@require_http_methods(["PATCH"])
def my_notification_detail_view(request: HttpRequest, org_id, notification_id) -> JsonResponse:
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_membership(
        user,
        org,
        allowed_roles={
            OrgMembership.Role.ADMIN,
            OrgMembership.Role.PM,
            OrgMembership.Role.MEMBER,
            OrgMembership.Role.CLIENT,
        },
    )
    if membership is None:
        return _json_error("forbidden", status=403)

    notification = (
        InAppNotification.objects.filter(id=notification_id, org=org, recipient_user=user)
        .select_related("event")
        .first()
    )
    if notification is None:
        return _json_error("not found", status=404)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    if "read" in payload:
        if bool(payload.get("read")) is not True:
            return _json_error("read can only be set to true", status=400)
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])

    return JsonResponse({"notification": _in_app_dict(notification)})


def _effective_preferences_payload(*, membership: OrgMembership, project: Project) -> list[dict]:
    payloads: list[dict] = []
    for event_type in NotificationEventType.values:
        for channel in NotificationChannel.values:
            effective = effective_preference_for_membership(
                membership=membership,
                project_id=project.id,
                event_type=event_type,
                channel=channel,
            )
            payloads.append(
                {
                    "event_type": event_type,
                    "channel": channel,
                    "enabled": bool(effective.enabled),
                }
            )
    return payloads


@require_http_methods(["GET", "PATCH"])
def notification_preferences_view(request: HttpRequest, org_id, project_id) -> JsonResponse:
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_membership(
        user,
        org,
        allowed_roles={
            OrgMembership.Role.ADMIN,
            OrgMembership.Role.PM,
            OrgMembership.Role.MEMBER,
            OrgMembership.Role.CLIENT,
        },
    )
    if membership is None:
        return _json_error("forbidden", status=403)

    project = _require_project(org, project_id)
    if project is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        return JsonResponse(
            {"preferences": _effective_preferences_payload(membership=membership, project=project)}
        )

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    updates = payload.get("preferences")
    if not isinstance(updates, list):
        return _json_error("preferences must be a list", status=400)

    allowed_event_types = set(NotificationEventType.values)
    allowed_channels = set(NotificationChannel.values)

    for row in updates:
        if not isinstance(row, dict):
            return _json_error("preferences entries must be objects", status=400)
        event_type = str(row.get("event_type", "")).strip()
        channel = str(row.get("channel", "")).strip()
        if event_type not in allowed_event_types:
            return _json_error("invalid event_type", status=400)
        if channel not in allowed_channels:
            return _json_error("invalid channel", status=400)
        enabled = bool(row.get("enabled", False))

        NotificationPreference.objects.update_or_create(
            org=org,
            project=project,
            user=user,
            event_type=event_type,
            channel=channel,
            defaults={"enabled": enabled},
        )

    return JsonResponse(
        {"preferences": _effective_preferences_payload(membership=membership, project=project)}
    )


@require_http_methods(["GET", "PATCH"])
def notification_project_settings_view(request: HttpRequest, org_id, project_id) -> JsonResponse:
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_membership(
        user,
        org,
        allowed_roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM},
    )
    if membership is None:
        return _json_error("forbidden", status=403)

    project = _require_project(org, project_id)
    if project is None:
        return _json_error("not found", status=404)

    def _payload() -> list[dict]:
        payloads: list[dict] = []
        for event_type in NotificationEventType.values:
            for channel in NotificationChannel.values:
                setting = ProjectNotificationSetting.objects.filter(
                    project=project, event_type=event_type, channel=channel
                ).first()
                enabled = True if setting is None else bool(setting.enabled)
                payloads.append({"event_type": event_type, "channel": channel, "enabled": enabled})
        return payloads

    if request.method == "GET":
        return JsonResponse({"settings": _payload()})

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    updates = payload.get("settings")
    if not isinstance(updates, list):
        return _json_error("settings must be a list", status=400)

    allowed_event_types = set(NotificationEventType.values)
    allowed_channels = set(NotificationChannel.values)

    for row in updates:
        if not isinstance(row, dict):
            return _json_error("settings entries must be objects", status=400)
        event_type = str(row.get("event_type", "")).strip()
        channel = str(row.get("channel", "")).strip()
        if event_type not in allowed_event_types:
            return _json_error("invalid event_type", status=400)
        if channel not in allowed_channels:
            return _json_error("invalid channel", status=400)
        enabled = bool(row.get("enabled", False))

        ProjectNotificationSetting.objects.update_or_create(
            org=org,
            project=project,
            event_type=event_type,
            channel=channel,
            defaults={"enabled": enabled},
        )

    return JsonResponse({"settings": _payload()})


@require_http_methods(["GET"])
def notification_delivery_logs_view(request: HttpRequest, org_id, project_id) -> JsonResponse:
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_membership(
        user,
        org,
        allowed_roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM},
    )
    if membership is None:
        return _json_error("forbidden", status=403)

    project = _require_project(org, project_id)
    if project is None:
        return _json_error("not found", status=404)

    status_filter = str(request.GET.get("status", "")).strip()
    allowed_statuses = {"", "success", "failure", "queued"}
    if status_filter not in allowed_statuses:
        return _json_error("invalid status", status=400)

    try:
        limit = _normalize_limit(request.GET.get("limit"))
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    qs = EmailDeliveryLog.objects.filter(org=org, project=project)
    if status_filter:
        qs = qs.filter(status=status_filter)
    qs = qs.filter(Q(notification_event__isnull=False) | Q(outbound_draft__isnull=False))
    qs = qs.order_by("-queued_at", "-id")[:limit]
    return JsonResponse({"deliveries": [_delivery_log_dict(r) for r in qs]})
