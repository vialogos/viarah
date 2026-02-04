from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

logger = logging.getLogger(__name__)


def publish_org_event(*, org_id: uuid.UUID, event_type: str, data: dict[str, Any]) -> None:
    """Best-effort publish of an org-scoped WS event.

    This must never break the REST request flow if WS/Redis is unavailable.
    """

    payload = {
        "event_id": str(uuid.uuid4()),
        "occurred_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "org_id": str(org_id),
        "type": event_type,
        "data": data,
    }

    def _send() -> None:
        try:
            channel_layer = get_channel_layer()
            if channel_layer is None:
                return

            async_to_sync(channel_layer.group_send)(
                f"org.{org_id}",
                {
                    "type": "org.event",
                    "event": payload,
                },
            )
        except Exception:
            logger.exception(
                "realtime publish failed",
                extra={"org_id": str(org_id), "event_type": event_type},
            )

    try:
        transaction.on_commit(_send)
    except Exception:
        logger.exception(
            "realtime publish registration failed",
            extra={"org_id": str(org_id), "event_type": event_type},
        )
