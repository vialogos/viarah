from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from identity.models import OrgMembership
from work_items.models import ProjectMembership

from .models import (
    EmailDeliveryLog,
    EmailDeliveryStatus,
    InAppNotification,
    NotificationChannel,
    NotificationEvent,
    NotificationEventType,
    NotificationPreference,
    ProjectNotificationSetting,
)

logger = logging.getLogger(__name__)


MAX_IN_APP_QUERY_LIMIT = 200


class NotificationDispatchError(Exception):
    """Raised when a notification event cannot be emitted due to invalid inputs/config."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class EffectivePreference:
    """Computed effective preference for a membership, after applying project + user settings."""

    enabled: bool
    user_enabled: bool
    project_enabled: bool


def _default_user_preference_enabled(*, role: str, event_type: str, channel: str) -> bool:
    if role in {OrgMembership.Role.ADMIN, OrgMembership.Role.PM, OrgMembership.Role.MEMBER}:
        if channel == NotificationChannel.IN_APP:
            return True
        if channel == NotificationChannel.EMAIL:
            return event_type in {
                NotificationEventType.ASSIGNMENT_CHANGED,
                NotificationEventType.REPORT_PUBLISHED,
            }
        return False

    if role == OrgMembership.Role.CLIENT:
        if channel == NotificationChannel.IN_APP:
            return event_type in {
                NotificationEventType.REPORT_PUBLISHED,
                NotificationEventType.COMMENT_CREATED,
            }
        if channel == NotificationChannel.EMAIL:
            return event_type == NotificationEventType.REPORT_PUBLISHED
        return False

    return False


def _project_setting_enabled(*, project_id, event_type: str, channel: str) -> bool:
    setting = ProjectNotificationSetting.objects.filter(
        project_id=project_id,
        event_type=event_type,
        channel=channel,
    ).first()
    if setting is None:
        return True
    return bool(setting.enabled)


def _user_preference_enabled(
    *, user_id, project_id, event_type: str, channel: str, role: str
) -> bool:
    pref = NotificationPreference.objects.filter(
        user_id=user_id,
        project_id=project_id,
        event_type=event_type,
        channel=channel,
    ).first()
    if pref is None:
        return _default_user_preference_enabled(role=role, event_type=event_type, channel=channel)
    return bool(pref.enabled)


def effective_preference_for_membership(
    *, membership: OrgMembership, project_id, event_type: str, channel: str
) -> EffectivePreference:
    """Compute whether a given membership should receive an event on a channel.

    The effective value is `project_enabled AND user_enabled`.
    User preference defaults are role- and event-specific when no explicit override exists.
    """
    project_enabled = _project_setting_enabled(
        project_id=project_id, event_type=event_type, channel=channel
    )
    user_enabled = _user_preference_enabled(
        user_id=membership.user_id,
        project_id=project_id,
        event_type=event_type,
        channel=channel,
        role=membership.role,
    )
    return EffectivePreference(
        enabled=project_enabled and user_enabled,
        project_enabled=project_enabled,
        user_enabled=user_enabled,
    )


def _notification_email_subject(event_type: str) -> str:
    if event_type == NotificationEventType.ASSIGNMENT_CHANGED:
        return "ViaRah: assignment updated"
    if event_type == NotificationEventType.STATUS_CHANGED:
        return "ViaRah: status updated"
    if event_type == NotificationEventType.COMMENT_CREATED:
        return "ViaRah: new comment"
    if event_type == NotificationEventType.REPORT_PUBLISHED:
        return "ViaRah: report published"
    return "ViaRah: notification"


def _notification_email_body(*, org_name: str, project_name: str | None, event_type: str) -> str:
    parts = [f"You have a new ViaRah notification ({event_type})."]
    parts.append(f"Org: {org_name}")
    if project_name:
        parts.append(f"Project: {project_name}")
    parts.append("")
    parts.append("Log in to ViaRah to view details.")
    return "\n".join(parts)


def _from_email() -> str:
    return str(getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip() or "no-reply@viarah.local"


def notification_email_content(
    *, org_name: str, project_name: str | None, event_type: str
) -> tuple[str, str]:
    """Return a best-effort (subject, body) pair for an email notification event."""
    return (
        _notification_email_subject(event_type),
        _notification_email_body(
            org_name=org_name, project_name=project_name, event_type=event_type
        ),
    )


def _enqueue_delivery_log(log_id: str) -> None:
    from .tasks import send_email_delivery

    def _enqueue() -> None:
        try:
            send_email_delivery.delay(str(log_id))
        except Exception:
            logger.exception(
                "email delivery enqueue failed", extra={"delivery_log_id": str(log_id)}
            )
            EmailDeliveryLog.objects.filter(id=log_id).update(
                status=EmailDeliveryStatus.FAILURE,
                error_code="enqueue_failed",
                error_detail="failed to enqueue delivery task",
                updated_at=timezone.now(),
            )

    try:
        transaction.on_commit(_enqueue)
    except Exception:
        logger.exception(
            "email delivery enqueue registration failed", extra={"delivery_log_id": str(log_id)}
        )


def emit_project_event(
    *,
    org,
    project,
    event_type: str,
    actor_user,
    data: dict[str, Any],
    client_visible: bool,
) -> NotificationEvent:
    """Emit a project-scoped notification event and fan out deliveries (in-app + email)."""

    if event_type not in set(NotificationEventType.values):
        raise NotificationDispatchError("invalid event_type")

    include_clients = bool(client_visible)
    allowed_roles = {
        OrgMembership.Role.ADMIN,
        OrgMembership.Role.PM,
        OrgMembership.Role.MEMBER,
    }
    if include_clients:
        allowed_roles.add(OrgMembership.Role.CLIENT)

    memberships = list(
        OrgMembership.objects.filter(org=org, role__in=allowed_roles)
        .select_related("org", "user")
        .order_by("created_at", "id")
    )

    actor_user_id = getattr(actor_user, "id", None) if actor_user is not None else None
    if actor_user_id is not None:
        memberships = [m for m in memberships if str(m.user_id) != str(actor_user_id)]

    project_member_user_ids = set(
        ProjectMembership.objects.filter(project_id=project.id).values_list("user_id", flat=True)
    )
    memberships = [
        membership
        for membership in memberships
        if membership.role in {OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
        or membership.user_id in project_member_user_ids
    ]

    with transaction.atomic():
        event = NotificationEvent.objects.create(
            org=org,
            project=project,
            event_type=event_type,
            actor_user=actor_user,
            data_json=data or {},
        )

        in_app_rows: list[InAppNotification] = []
        email_log_ids: list[str] = []

        for membership in memberships:
            in_app_pref = effective_preference_for_membership(
                membership=membership,
                project_id=project.id,
                event_type=event_type,
                channel=NotificationChannel.IN_APP,
            )
            if in_app_pref.enabled:
                in_app_rows.append(
                    InAppNotification(
                        org=org,
                        project=project,
                        event=event,
                        recipient_user_id=membership.user_id,
                        read_at=None,
                    )
                )

            email_pref = effective_preference_for_membership(
                membership=membership,
                project_id=project.id,
                event_type=event_type,
                channel=NotificationChannel.EMAIL,
            )
            if not email_pref.enabled:
                continue

            recipient_email = str(getattr(membership.user, "email", "") or "").strip()
            if not recipient_email:
                continue

            log = EmailDeliveryLog.objects.create(
                org=org,
                project=project,
                notification_event=event,
                outbound_draft=None,
                recipient_user_id=membership.user_id,
                to_email=recipient_email,
                subject=_notification_email_subject(event_type),
                status=EmailDeliveryStatus.QUEUED,
                attempt_number=0,
                error_code="",
                error_detail="",
                sent_at=None,
            )
            email_log_ids.append(str(log.id))

        if in_app_rows:
            InAppNotification.objects.bulk_create(in_app_rows)

    for log_id in email_log_ids:
        _enqueue_delivery_log(log_id)

    # Push delivery fanout is queued after commit to avoid partial dispatch.
    push_user_ids: list[str] = []
    for membership in memberships:
        push_pref = effective_preference_for_membership(
            membership=membership,
            project_id=project.id,
            event_type=event_type,
            channel=NotificationChannel.PUSH,
        )
        if push_pref.enabled:
            push_user_ids.append(str(membership.user_id))

    if push_user_ids:
        from push.services import push_is_configured
        from push.tasks import send_push_for_notification_event

        if push_is_configured():
            event_id = str(event.id)

            def _enqueue_push() -> None:
                for user_id in push_user_ids:
                    try:
                        send_push_for_notification_event.delay(event_id, user_id)
                    except Exception:
                        logger.exception(
                            "push delivery enqueue failed",
                            extra={"event_id": event_id, "recipient_user_id": str(user_id)},
                        )

            try:
                transaction.on_commit(_enqueue_push)
            except Exception:
                logger.exception("push enqueue registration failed", extra={"event_id": event_id})

    return event


def emit_assignment_changed(
    *,
    org,
    project,
    actor_user,
    task_id: str,
    old_assignee_user_id: str | None,
    new_assignee_user_id: str | None,
) -> NotificationEvent | None:
    """Emit an assignment-changed event to the new assignee (excluding the actor).

    Side effects: Creates a `NotificationEvent`, persists in-app rows, and enqueues email + push
    delivery when enabled by effective preferences.
    """
    if not new_assignee_user_id:
        return None

    membership = (
        OrgMembership.objects.filter(org=org, user_id=new_assignee_user_id)
        .select_related("org", "user")
        .first()
    )
    if membership is None:
        return None

    if not ProjectMembership.objects.filter(
        project_id=project.id,
        user_id=membership.user_id,
    ).exists():
        return None

    # Actor excluded.
    actor_user_id = getattr(actor_user, "id", None) if actor_user is not None else None
    if actor_user_id is not None and str(actor_user_id) == str(new_assignee_user_id):
        return None

    with transaction.atomic():
        event = NotificationEvent.objects.create(
            org=org,
            project=project,
            event_type=NotificationEventType.ASSIGNMENT_CHANGED,
            actor_user=actor_user,
            data_json={
                "work_item_type": "task",
                "work_item_id": str(task_id),
                "old_assignee_user_id": str(old_assignee_user_id) if old_assignee_user_id else None,
                "new_assignee_user_id": str(new_assignee_user_id),
            },
        )

        in_app_pref = effective_preference_for_membership(
            membership=membership,
            project_id=project.id,
            event_type=NotificationEventType.ASSIGNMENT_CHANGED,
            channel=NotificationChannel.IN_APP,
        )
        if in_app_pref.enabled:
            InAppNotification.objects.create(
                org=org,
                project=project,
                event=event,
                recipient_user_id=new_assignee_user_id,
                read_at=None,
            )

        email_pref = effective_preference_for_membership(
            membership=membership,
            project_id=project.id,
            event_type=NotificationEventType.ASSIGNMENT_CHANGED,
            channel=NotificationChannel.EMAIL,
        )
        if email_pref.enabled:
            recipient_email = str(getattr(membership.user, "email", "") or "").strip()
            if recipient_email:
                log = EmailDeliveryLog.objects.create(
                    org=org,
                    project=project,
                    notification_event=event,
                    outbound_draft=None,
                    recipient_user_id=new_assignee_user_id,
                    to_email=recipient_email,
                    subject=_notification_email_subject(NotificationEventType.ASSIGNMENT_CHANGED),
                    status=EmailDeliveryStatus.QUEUED,
                    attempt_number=0,
                    error_code="",
                    error_detail="",
                    sent_at=None,
                )
                _enqueue_delivery_log(str(log.id))

    # Push delivery fanout is queued after commit to avoid partial dispatch.
    push_pref = effective_preference_for_membership(
        membership=membership,
        project_id=project.id,
        event_type=NotificationEventType.ASSIGNMENT_CHANGED,
        channel=NotificationChannel.PUSH,
    )
    if push_pref.enabled:
        from push.services import push_is_configured

        if push_is_configured():
            from push.models import PushSubscription
            from push.tasks import send_push_for_notification_event

            event_id = str(event.id)
            recipient_user_id = str(new_assignee_user_id)

            def _enqueue_push() -> None:
                if not PushSubscription.objects.filter(user_id=recipient_user_id).exists():
                    return

                try:
                    send_push_for_notification_event.delay(event_id, recipient_user_id)
                except Exception:
                    logger.exception(
                        "push delivery enqueue failed",
                        extra={"event_id": event_id, "recipient_user_id": recipient_user_id},
                    )

            try:
                transaction.on_commit(_enqueue_push)
            except Exception:
                logger.exception("push enqueue registration failed", extra={"event_id": event_id})

    return event


def emit_report_published(
    *,
    org,
    project,
    actor_user,
    report_run_id: str,
    share_link_id: str,
    expires_at: datetime.datetime | None,
) -> NotificationEvent:
    """Emit a report-published event (client-visible) with share-link context."""
    data: dict[str, Any] = {
        "report_run_id": str(report_run_id),
        "share_link_id": str(share_link_id),
        "expires_at": expires_at.isoformat() if expires_at else None,
    }
    return emit_project_event(
        org=org,
        project=project,
        event_type=NotificationEventType.REPORT_PUBLISHED,
        actor_user=actor_user,
        data=data,
        client_visible=True,
    )
