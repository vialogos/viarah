from __future__ import annotations

import json
import uuid

from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from identity.models import Org, OrgMembership
from work_items.models import Project, ProjectMembership, Subtask, Task

from .models import (
    EmailDeliveryLog,
    InAppNotification,
    NotificationChannel,
    NotificationEvent,
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


def _get_api_key_principal(request: HttpRequest):
    return getattr(request, "api_key_principal", None)


def _principal_has_scope(principal, required: str) -> bool:
    scopes = set(getattr(principal, "scopes", None) or [])
    if required == "read":
        return "read" in scopes or "write" in scopes
    return required in scopes


def _principal_project_id(principal) -> uuid.UUID | None:
    project_id = getattr(principal, "project_id", None)
    if project_id is None or not str(project_id).strip():
        return None
    try:
        return uuid.UUID(str(project_id))
    except (TypeError, ValueError):
        return None


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
        "data": dict(getattr(event, "data_json", None) or {}) if event is not None else {},
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


def _parse_project_id_query(request: HttpRequest) -> tuple[uuid.UUID | None, JsonResponse | None]:
    project_id_raw = request.GET.get("project_id")
    if project_id_raw is None or not str(project_id_raw).strip():
        return None, None
    try:
        return uuid.UUID(str(project_id_raw)), None
    except (TypeError, ValueError):
        return None, _json_error("project_id must be a UUID", status=400)


def _enrich_notification_payloads_with_titles(payloads: list[dict]) -> None:
    """
    Best-effort title hydration for existing notification rows where emitters omitted titles.

    This keeps the notification UX stable even when older rows are still present in the DB.
    """

    task_ids: set[uuid.UUID] = set()
    subtask_ids: set[uuid.UUID] = set()

    for payload in payloads:
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            continue
        if str(data.get("work_item_title", "")).strip():
            continue
        work_item_type = str(data.get("work_item_type", "")).strip()
        work_item_id_raw = str(data.get("work_item_id", "")).strip()
        if not work_item_type or not work_item_id_raw:
            continue
        try:
            work_item_id = uuid.UUID(work_item_id_raw)
        except (TypeError, ValueError):
            continue
        if work_item_type == "task":
            task_ids.add(work_item_id)
        elif work_item_type == "subtask":
            subtask_ids.add(work_item_id)

    task_titles_by_id: dict[str, str] = {}
    if task_ids:
        for row in Task.objects.filter(id__in=task_ids).only("id", "title"):
            task_titles_by_id[str(row.id)] = row.title

    subtask_titles_by_id: dict[str, str] = {}
    if subtask_ids:
        for row in Subtask.objects.filter(id__in=subtask_ids).only("id", "title"):
            subtask_titles_by_id[str(row.id)] = row.title

    if not task_titles_by_id and not subtask_titles_by_id:
        return

    for payload in payloads:
        data = payload.get("data")
        if not isinstance(data, dict):
            continue
        if str(data.get("work_item_title", "")).strip():
            continue
        work_item_type = str(data.get("work_item_type", "")).strip()
        work_item_id = str(data.get("work_item_id", "")).strip()
        if work_item_type == "task":
            title = task_titles_by_id.get(work_item_id, "")
        elif work_item_type == "subtask":
            title = subtask_titles_by_id.get(work_item_id, "")
        else:
            title = ""
        if title:
            data["work_item_title"] = title


@require_http_methods(["GET"])
def my_notifications_collection_view(request: HttpRequest, org_id) -> JsonResponse:
    """List in-app notifications for the current user.

    Auth: Session-only (see `docs/api/scope-map.yaml` operation
    `notifications__my_notifications_get`).
    Inputs: Path `org_id`; optional query `project_id`, `unread_only`, `limit`.
    Returns: `{notifications: [...]}` (most recent first).
    Side effects: None.
    """
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

    project_id, err = _parse_project_id_query(request)
    if err is not None:
        return err

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
    payloads = [_in_app_dict(n) for n in rows]
    _enrich_notification_payloads_with_titles(payloads)
    return JsonResponse({"notifications": payloads})


@require_http_methods(["GET"])
def my_notifications_badge_view(request: HttpRequest, org_id) -> JsonResponse:
    """Return an unread notification count for the current user.

    Auth: Session-only (see `docs/api/scope-map.yaml` operation
    `notifications__my_notifications_badge_get`).
    Inputs: Path `org_id`; optional query `project_id`.
    Returns: `{unread_count}`.
    Side effects: None.
    """
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

    project_id, err = _parse_project_id_query(request)
    if err is not None:
        return err

    qs = InAppNotification.objects.filter(org=org, recipient_user=user, read_at__isnull=True)
    if project_id is not None:
        qs = qs.filter(project_id=project_id)

    return JsonResponse({"unread_count": qs.count()})


@require_http_methods(["POST"])
def my_notifications_mark_all_read_view(request: HttpRequest, org_id) -> JsonResponse:
    """Mark all unread in-app notifications as read for the current user.

    Auth: Session-only.
    Inputs: Path `org_id`; optional query `project_id`.
    Returns: `{updated_count}`.
    Side effects: Sets `read_at` timestamp on unread notifications.
    """

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

    project_id, err = _parse_project_id_query(request)
    if err is not None:
        return err

    qs = InAppNotification.objects.filter(org=org, recipient_user=user, read_at__isnull=True)
    if project_id is not None:
        qs = qs.filter(project_id=project_id)

    now = timezone.now()
    updated_count = int(qs.update(read_at=now))

    try:
        from realtime.services import publish_org_event

        publish_org_event(
            org_id=org.id,
            event_type="notifications.updated",
            data={"project_id": str(project_id) if project_id else ""},
        )
    except Exception:
        pass

    return JsonResponse({"updated_count": updated_count})


@require_http_methods(["PATCH"])
def my_notification_detail_view(request: HttpRequest, org_id, notification_id) -> JsonResponse:
    """Update a single in-app notification for the current user.

    Auth: Session-only (see `docs/api/scope-map.yaml` operation
    `notifications__my_notification_patch`).
    Inputs: Path `org_id`, `notification_id`; JSON supports `{read: true}`.
    Returns: `{notification}`.
    Side effects: Setting `read=true` stores a `read_at` timestamp.
    """
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
            try:
                from realtime.services import publish_org_event

                publish_org_event(
                    org_id=org.id,
                    event_type="notifications.updated",
                    data={
                        "project_id": str(notification.project_id)
                        if notification.project_id
                        else "",
                    },
                )
            except Exception:
                pass

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
    """Get or update per-user notification preferences for a project.

    Auth: Session-only (see `docs/api/scope-map.yaml` operations
    `notifications__notification_preferences_get` and
    `notifications__notification_preferences_patch`).
    Inputs: Path `org_id`, `project_id`; PATCH JSON `preferences` list.
    Each entry: `{event_type, channel, enabled}`.
    Returns: `{preferences: [...]}` (effective preferences after applying defaults and overrides).
    Side effects: PATCH upserts `NotificationPreference` rows for the current user.
    """
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

    if membership.role in {OrgMembership.Role.MEMBER, OrgMembership.Role.CLIENT}:
        if not ProjectMembership.objects.filter(project=project, user=user).exists():
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
    """Get or update project-level notification settings (defaults).

    Auth: Session-only (ADMIN/PM) (see `docs/api/scope-map.yaml` operations
    `notifications__notification_settings_get` and `notifications__notification_settings_patch`).
    Inputs: Path `org_id`, `project_id`; PATCH JSON `{settings: [{event_type, channel, enabled}]}`.
    Returns: `{settings: [...]}`.
    Side effects: PATCH upserts `ProjectNotificationSetting` rows.
    """
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
    """List email delivery attempts for a project.

    Auth: Session-only (ADMIN/PM) (see `docs/api/scope-map.yaml` operation
    `notifications__notification_delivery_logs_get`).
    Inputs: Path `org_id`, `project_id`; optional query `status` and `limit`.
    Returns: `{deliveries: [...]}` ordered by most recently queued.
    Side effects: None.
    """
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


@require_http_methods(["GET"])
def project_notification_events_view(request: HttpRequest, org_id, project_id) -> JsonResponse:
    """List recent notification events for a project (client-safe projection).

    Auth: Session (ADMIN/PM) or API key (read) (see `docs/api/scope-map.yaml` operation
    `notifications__notification_events_get`).
    Inputs: Path `org_id`, `project_id`; optional query `limit`. API keys may be project-restricted.
    Returns: `{events: [{id, event_type, created_at}]}`.
    Side effects: None.
    """
    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    project = _require_project(org, project_id)
    if project is None:
        return _json_error("not found", status=404)

    principal = _get_api_key_principal(request)
    if principal is not None:
        if str(org.id) != str(principal.org_id):
            return _json_error("forbidden", status=403)
        if not _principal_has_scope(principal, "read"):
            return _json_error("forbidden", status=403)

        project_restriction = _principal_project_id(principal)
        if project_restriction is not None and str(project_restriction) != str(project.id):
            return _json_error("forbidden", status=403)
    else:
        if not request.user.is_authenticated:
            return _json_error("unauthorized", status=401)
        membership = _require_membership(
            request.user,
            org,
            allowed_roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM},
        )
        if membership is None:
            return _json_error("forbidden", status=403)

    try:
        limit = _normalize_limit(request.GET.get("limit"))
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    rows = list(
        NotificationEvent.objects.filter(org=org, project=project).order_by("-created_at", "-id")[
            :limit
        ]
    )
    return JsonResponse(
        {
            "events": [
                {
                    "id": str(e.id),
                    "event_type": e.event_type,
                    "created_at": e.created_at.isoformat(),
                }
                for e in rows
            ]
        }
    )
