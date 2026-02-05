# push

Push provides Web Push subscription management and delivery for notification events.

## Key entrypoints

- `push/models.py` — `PushSubscription`
- `push/views.py`, `push/urls.py` — subscription CRUD + VAPID public key endpoint
- `push/services.py` — VAPID configuration checks + `pywebpush` integration
- `push/tasks.py` — delivery task (`send_push_for_notification_event`)
- `docs/web-push.md` — detailed operator notes (HTTPS/VAPID)

## Models

- `PushSubscription` — stores endpoint + key material for a user’s push subscription

## API routes

Mounted under `/api/`:

- `/api/push/vapid_public_key` → `push.views.vapid_public_key_view`
- `/api/push/subscriptions` → `push.views.subscriptions_collection_view`
- `/api/push/subscriptions/<subscription_id>` → `push.views.subscription_detail_view`

The canonical contract is `docs/api/openapi.yaml` + `docs/api/scope-map.yaml`.

## Auth / access control

Push endpoints require a session user and explicitly forbid API keys (see `_require_session_user()`
in `push/views.py`).

## Background jobs / tasks

- `push.tasks.send_push_for_notification_event()` delivers a push message to the recipient’s active
  `PushSubscription` rows.
- It’s enqueued from `notifications/services.py` when:
  - push is configured (`push.services.push_is_configured()`), and
  - effective preferences allow the push channel.

## Config / env vars

Push delivery is enabled when all of these are set (see `.env.example`):

- `WEBPUSH_VAPID_PUBLIC_KEY`
- `WEBPUSH_VAPID_PRIVATE_KEY`
- `WEBPUSH_VAPID_SUBJECT`
