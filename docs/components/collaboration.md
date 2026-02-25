# collaboration

Collaboration provides comments and attachments on tasks and epics, with client-safe filtering and
sanitized Markdown rendering.

## Key entrypoints

- `collaboration/models.py` — `Comment`, `Attachment`
- `collaboration/services.py` — Markdown sanitization + attachment SHA256
- `collaboration/views.py`, `collaboration/urls.py` — REST API + file download

## Models

- `Comment` — exactly one target (`task` XOR `epic`), stores markdown + rendered HTML + `client_safe`
- `Attachment` — exactly one target (`task` XOR `epic`); stored via `FileField` with deterministic path

## API routes

Mounted under `/api/`:

- `/api/orgs/<org_id>/tasks/<task_id>/comments` → `collaboration.views.task_comments_collection_view`
- `/api/orgs/<org_id>/epics/<epic_id>/comments` → `collaboration.views.epic_comments_collection_view`
- `/api/orgs/<org_id>/tasks/<task_id>/attachments` → `collaboration.views.task_attachments_collection_view`
- `/api/orgs/<org_id>/epics/<epic_id>/attachments` → `collaboration.views.epic_attachments_collection_view`
- `/api/orgs/<org_id>/attachments/<attachment_id>/download` → `collaboration.views.attachment_download_view`

The canonical contract is `docs/api/openapi.yaml` + `docs/api/scope-map.yaml`.

## Auth / access control

Collaboration endpoints require a session user and explicitly forbid API keys (see
`_require_session_user()` in `collaboration/views.py`).

Client visibility:

- If the org membership role is `client`, comment listing and attachment access are filtered by
  `client_safe` flags and may return `404` for non-client-safe targets.

## Interactions / dependencies

- Writes audit events (`audit.services.write_audit_event`) for comment/attachment actions.
- Publishes realtime “comment.created” events via `realtime.services.publish_org_event`.
- Emits project notifications (`notifications.services.emit_project_event`) for comment creation.
