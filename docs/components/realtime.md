# realtime

Realtime provides an org-scoped websocket event stream for the SPA. The stream is read-only and
intentionally IDs-only; clients refetch authoritative objects over REST.

## Key entrypoints

- `viarah/asgi.py` — protocol router + websocket middleware stack + origin validator
- `realtime/routing.py` — websocket URL pattern(s)
- `realtime/consumers.py` — `OrgEventsConsumer` (membership-gated)
- `realtime/services.py` — `publish_org_event()` helper
- `viarah/settings/base.py` — `CHANNEL_LAYERS` configuration (Redis)

## Websocket route

- `/ws/orgs/<org_id>/events` → `realtime.consumers.OrgEventsConsumer`

## Auth / access control

- Session-only (cookies via `AuthMiddlewareStack`).
- `OrgEventsConsumer.connect()` enforces org membership for roles `admin`/`pm`/`member` before joining
  the org group (`org.<org_id>`).

## Event payload shape

`realtime.services.publish_org_event()` emits a payload like:

- `event_id` (UUID)
- `occurred_at` (UTC ISO-8601)
- `org_id`
- `type` (event type string, e.g. `comment.created`)
- `data` (IDs and small metadata)

Delivery is best-effort: publish is registered via `transaction.on_commit()` and failures are
swallowed (logged) so REST flows continue even if Redis/Channels is unavailable.

## Interactions / dependencies

- Collaboration and work item endpoints publish org events for comment/work updates.
