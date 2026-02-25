# outbound_comms

Outbound comms provides “draft then send” flows for outbound emails and outbound comments. Drafts
are rendered from templates, then either queued for email delivery or written as collaboration
comments.

## Key entrypoints

- `outbound_comms/models.py` — `OutboundDraft` (+ enums: type/status/work item type)
- `outbound_comms/services.py` — `create_outbound_draft()`, `send_outbound_draft()`
- `outbound_comms/views.py`, `outbound_comms/urls.py` — REST API

## Models

- `OutboundDraft` — org/project-scoped draft:
  - `type=email` drafts store recipient user IDs + subject/body markdown
  - `type=comment` drafts store `work_item_type` + `work_item_id` and optional `comment_client_safe`

## API routes

Mounted under `/api/`:

- `/api/orgs/<org_id>/projects/<project_id>/outbound-drafts` → `outbound_comms.views.outbound_drafts_collection_view`
- `/api/orgs/<org_id>/outbound-drafts/<draft_id>` → `outbound_comms.views.outbound_draft_detail_view`
- `/api/orgs/<org_id>/outbound-drafts/<draft_id>/send` → `outbound_comms.views.outbound_draft_send_view`

The canonical contract is `docs/api/openapi.yaml` + `docs/api/scope-map.yaml`.

## Auth / access control

Outbound comms endpoints require a session user and explicitly forbid API keys (see
`_require_session_user()` in `outbound_comms/views.py`).

## Delivery behavior

- Email drafts:
  - Validate recipient users are org members (`OrgMembership`).
  - Create `notifications.EmailDeliveryLog` rows and enqueue delivery via
    `notifications.services._enqueue_delivery_log()` (which calls the Celery task).
- Comment drafts:
  - Create a `collaboration.Comment` on the target task/epic using sanitized HTML rendering.
  - Publish a realtime event (`realtime.services.publish_org_event`) and emit a notification event
    (`notifications.services.emit_project_event`).

## Interactions / dependencies

- Depends on `templates` for draft rendering (Liquid templates).
- Writes audit events via `audit.services.write_audit_event`.
