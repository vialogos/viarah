from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from pywebpush import WebPushException

from notifications.models import NotificationEvent, NotificationEventType

from .models import PushSubscription
from .services import push_is_configured, send_push_to_subscription

logger = logging.getLogger(__name__)


def _payload_for_event(*, event: NotificationEvent) -> dict[str, Any]:
    data = dict(getattr(event, "data_json", {}) or {})
    payload: dict[str, Any] = {
        "title": "ViaRah notification",
        "body": "You have a new notification.",
        "url": "/",
        "event_type": str(event.event_type),
        "project_id": str(event.project_id) if event.project_id else None,
    }

    if event.event_type == NotificationEventType.COMMENT_CREATED:
        payload.update({"title": "ViaRah: new comment", "body": "A new comment was posted."})

    if event.event_type == NotificationEventType.REPORT_PUBLISHED:
        report_run_id = str(data.get("report_run_id", "") or "").strip()
        if report_run_id and event.org_id:
            payload["url"] = f"/api/orgs/{event.org_id}/report-runs/{report_run_id}/web-view"
        payload.update({"title": "ViaRah: report published", "body": "A report was published."})

    return payload


@shared_task(
    bind=True,
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def send_push_for_notification_event(self, event_id: str, recipient_user_id: str) -> None:  # noqa: ARG001
    if not push_is_configured():
        return

    event = NotificationEvent.objects.filter(id=event_id).first()
    if event is None:
        return

    subs = list(PushSubscription.objects.filter(user_id=recipient_user_id).order_by("created_at"))
    if not subs:
        return

    payload = _payload_for_event(event=event)

    for sub in subs:
        try:
            send_push_to_subscription(subscription=sub, payload=payload)
        except WebPushException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in {404, 410}:
                PushSubscription.objects.filter(id=sub.id).delete()
                logger.info(
                    "push subscription deleted as stale",
                    extra={"subscription_id": str(sub.id), "status_code": int(status_code)},
                )
                continue

            logger.exception(
                "push delivery failed",
                extra={
                    "subscription_id": str(sub.id),
                    "status_code": int(status_code) if status_code is not None else None,
                    "event_id": str(event.id),
                },
            )
            raise
