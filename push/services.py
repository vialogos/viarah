from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from pywebpush import webpush

from .models import PushSubscription


def push_is_configured() -> bool:
    """Return True when the required VAPID settings are configured for Web Push delivery."""
    return bool(
        str(getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", "") or "").strip()
        and str(getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", "") or "").strip()
        and str(getattr(settings, "WEBPUSH_VAPID_SUBJECT", "") or "").strip()
    )


def vapid_public_key() -> str | None:
    """Return the configured VAPID public key (or None when missing)."""
    value = str(getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", "") or "").strip()
    return value or None


def send_push_to_subscription(*, subscription: PushSubscription, payload: dict[str, Any]) -> None:
    """Send a single Web Push message to one subscription.

    This is a best-effort operation: when push is not configured, it returns without raising.
    """
    if not push_is_configured():
        return

    private_key = str(getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", "") or "").strip()
    subject = str(getattr(settings, "WEBPUSH_VAPID_SUBJECT", "") or "").strip()
    if not private_key or not subject:
        return

    webpush(
        subscription_info={
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
        },
        data=json.dumps(payload or {}),
        vapid_private_key=private_key,
        vapid_claims={"sub": subject},
        ttl=60,
    )
