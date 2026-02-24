from __future__ import annotations

import logging

from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone

from .models import EmailDeliveryLog, EmailDeliveryStatus
from .services import _from_email, notification_email_content

logger = logging.getLogger(__name__)

def _publish_delivery_log_updated(*, log: EmailDeliveryLog, status: str) -> None:
    project_id = str(log.project_id) if log.project_id else ""
    if not project_id:
        return

    try:
        from realtime.services import publish_org_event

        publish_org_event(
            org_id=log.org_id,
            event_type="email_delivery_log.updated",
            data={
                "delivery_log_id": str(log.id),
                "project_id": project_id,
                "status": str(status),
            },
        )
    except Exception:
        return


@shared_task(
    bind=True,
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def send_email_delivery(self, delivery_log_id: str) -> None:  # noqa: ARG001
    """Send a queued email delivery for an `EmailDeliveryLog`.

    Trigger: Enqueued from `notifications.services` (and outbound email draft send fanout).
    Inputs: `delivery_log_id` is the `EmailDeliveryLog` UUID (string form).
    Idempotency: Safe to retry; returns early when the log is missing or already successful.
    Side effects: Sends email via Django `send_mail` and updates the delivery log status/attempts.
    Retries: Uses Celery autoretry (max_retries=5) for unexpected exceptions.
    """
    now = timezone.now()
    log = (
        EmailDeliveryLog.objects.select_related(
            "org",
            "project",
            "recipient_user",
            "notification_event",
            "outbound_draft",
        )
        .filter(id=delivery_log_id)
        .first()
    )
    if log is None:
        return

    if log.status == EmailDeliveryStatus.SUCCESS:
        return

    to_email = str(log.to_email or "").strip()
    if not to_email and log.recipient_user is not None:
        to_email = str(getattr(log.recipient_user, "email", "") or "").strip()

    if not to_email:
        EmailDeliveryLog.objects.filter(id=log.id).update(
            status=EmailDeliveryStatus.FAILURE,
            attempt_number=int(log.attempt_number or 0) + 1,
            error_code="missing_recipient_email",
            error_detail="recipient has no email",
            updated_at=now,
        )
        _publish_delivery_log_updated(log=log, status=EmailDeliveryStatus.FAILURE)
        return

    subject = str(log.subject or "").strip()
    body = ""
    if log.outbound_draft is not None:
        body = str(log.outbound_draft.body_markdown or "").strip()
        if not subject:
            subject = str(log.outbound_draft.subject or "").strip()

    if log.notification_event is not None:
        project_name = None
        if log.project is not None:
            project_name = str(getattr(log.project, "name", "") or "")
        fallback_subject, fallback_body = notification_email_content(
            org_name=str(log.org.name),
            project_name=project_name or None,
            event_type=str(log.notification_event.event_type),
        )
        if not subject:
            subject = fallback_subject
        if not body:
            body = fallback_body

    if not subject:
        subject = "ViaRah notification"
    if not body:
        body = "You have a new message in ViaRah."

    try:
        send_mail(subject, body, _from_email(), [to_email], fail_silently=False)
    except Exception as exc:
        logger.exception("email send failed", extra={"delivery_log_id": str(log.id)})
        EmailDeliveryLog.objects.filter(id=log.id).update(
            status=EmailDeliveryStatus.FAILURE,
            attempt_number=int(log.attempt_number or 0) + 1,
            error_code="smtp_error",
            error_detail=str(exc)[:2000],
            updated_at=now,
        )
        _publish_delivery_log_updated(log=log, status=EmailDeliveryStatus.FAILURE)
        raise

    EmailDeliveryLog.objects.filter(id=log.id).update(
        status=EmailDeliveryStatus.SUCCESS,
        attempt_number=int(log.attempt_number or 0) + 1,
        error_code="",
        error_detail="",
        sent_at=now,
        updated_at=now,
    )
    _publish_delivery_log_updated(log=log, status=EmailDeliveryStatus.SUCCESS)
