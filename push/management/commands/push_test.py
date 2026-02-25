from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from push.models import PushSubscription
from push.services import push_is_configured, send_push_to_subscription


class Command(BaseCommand):
    """Send a real Web Push notification to all subscriptions for a user.

    Usage:
      - `python manage.py push_test --email user@example.com [--title ...] [--body ...] [--url ...]`

    Operational notes:
      - Requires `WEBPUSH_VAPID_PUBLIC_KEY` and `WEBPUSH_VAPID_PRIVATE_KEY`.
      - Also requires `WEBPUSH_VAPID_SUBJECT` (typically via env vars / Django settings).
      - Side effects: sends real push notifications; safe to re-run but will re-send.
    """

    help = "Send a test push notification to all subscriptions for a user email."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--email", required=True, help="Recipient user email")
        parser.add_argument("--title", default="ViaRah test push", help="Notification title")
        parser.add_argument("--body", default="Test push from ViaRah", help="Notification body")
        parser.add_argument("--url", default="/", help="Click-through URL (relative)")

    def handle(self, *args, **options) -> None:
        if not push_is_configured():
            raise CommandError("push is not configured (missing WEBPUSH_VAPID_* env vars)")

        email = str(options.get("email") or "").strip().lower()
        if not email:
            raise CommandError("--email is required")

        user = get_user_model().objects.filter(email=email).first()
        if user is None:
            raise CommandError("user not found")

        subs = list(PushSubscription.objects.filter(user=user).order_by("created_at"))
        if not subs:
            raise CommandError("user has no push subscriptions")

        payload = {
            "title": str(options.get("title") or "").strip() or "ViaRah test push",
            "body": str(options.get("body") or "").strip() or "Test push from ViaRah",
            "url": str(options.get("url") or "").strip() or "/",
            "event_type": "test",
        }

        for sub in subs:
            send_push_to_subscription(subscription=sub, payload=payload)

        self.stdout.write(json.dumps({"sent": len(subs)}))
