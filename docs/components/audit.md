# audit

Audit stores append-only audit events and provides a safe helper for writing metadata.

## Key entrypoints

- `audit/models.py` — `AuditEvent`
- `audit/services.py` — `write_audit_event()`, `assert_metadata_is_safe()`
- `audit/views.py`, `audit/urls.py` — read API

## Models

- `AuditEvent`

## API routes

Mounted under `/api/`:

- `/api/orgs/<org_id>/audit-events` → `audit.views.list_audit_events_view`

See `docs/api/openapi.yaml` for the canonical response schema.

## Auth / access control

- Session-only (`@login_required`).
- Only org roles `admin` and `pm` can read events (see `identity.models.OrgMembership.Role`).

## Interactions / dependencies

- `write_audit_event()` is used across many apps (templates, workflows, work_items, collaboration,
  outbound_comms, integrations, etc.).
- `assert_metadata_is_safe()` prevents logging metadata keys that look like secrets (tokens,
  passwords, API keys).
