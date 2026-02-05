# Component inventory

This page is the canonical per-component map for ViaRah.

The component list is derived from `INSTALLED_APPS` in `viarah/settings/base.py`. Unless noted, API
routes are mounted under `/api/` via `viarah/urls.py`.

Auth and request/response contracts live in:

- `docs/api/openapi.yaml` (OpenAPI contract)
- `docs/api/scope-map.yaml` (session vs API key vs webhook scopes)

## Backend components

- [`identity`](identity.md) — users, orgs, memberships, invites; session auth endpoints.
  - Key files: `identity/models.py`, `identity/views.py`, `identity/urls.py`
  - Depends on: `audit` (writes audit events)
- [`audit`](audit.md) — append-only audit log events; metadata safety checks.
  - Key files: `audit/models.py`, `audit/services.py`, `audit/views.py`, `audit/urls.py`
  - Depends on: `identity` (org + actor user)
- [`api_keys`](api_keys.md) — API keys + bearer-token middleware for `/api/...`.
  - Key files: `api_keys/models.py`, `api_keys/services.py`, `api_keys/middleware.py`,
    `api_keys/views.py`, `api_keys/urls.py`
  - Depends on: `identity`, `audit`
- [`workflows`](workflows.md) — workflows and ordered stages; used for progress tracking.
  - Key files: `workflows/models.py`, `workflows/views.py`, `workflows/urls.py`
  - Depends on: `identity`, `audit`, `api_keys`
- [`work_items`](work_items.md) — projects, epics, tasks, subtasks; primary PM object graph.
  - Key files: `work_items/models.py`, `work_items/views.py`, `work_items/urls.py`,
    `work_items/progress.py`
  - Depends on: `identity`, `audit`, `workflows`, `customization`, `notifications`, `realtime`
- [`notifications`](notifications.md) — notification events, preferences, in-app rows, email logs.
  - Key files: `notifications/models.py`, `notifications/views.py`, `notifications/services.py`,
    `notifications/tasks.py`, `notifications/urls.py`
  - Depends on: `identity`, `work_items`, `outbound_comms`, `push`
- [`templates`](templates.md) — Liquid templates and versions for reports/emails/comments/SoWs.
  - Key files: `templates/models.py`, `templates/views.py`, `templates/services.py`, `templates/urls.py`
  - Depends on: `core` (Liquid validation), `identity`, `audit`
- [`reports`](reports.md) — report runs (HTML/PDF) and render logs.
  - Key files: `reports/models.py`, `reports/views.py`, `reports/services.py`, `reports/tasks.py`,
    `reports/pdf_rendering.py`
  - Depends on: `identity`, `work_items`, `templates`, `audit`
- [`sows`](sows.md) — SoW objects, versions, signers; PDF artifacts.
  - Key files: `sows/models.py`, `sows/views.py`, `sows/services.py`, `sows/tasks.py`
  - Depends on: `identity`, `work_items`, `templates`, `reports` (PDF renderer assets)
- [`share_links`](share_links.md) — public share links for report runs + access logs.
  - Key files: `share_links/models.py`, `share_links/views.py`, `share_links/services.py`,
    `share_links/public_urls.py`, `share_links/public_views.py`
  - Depends on: `identity`, `reports`, `api_keys`, `notifications`, `audit`
- [`collaboration`](collaboration.md) — comments and attachments on tasks/epics.
  - Key files: `collaboration/models.py`, `collaboration/views.py`, `collaboration/services.py`,
    `collaboration/urls.py`
  - Depends on: `identity`, `work_items`, `notifications`, `realtime`, `audit`
- [`outbound_comms`](outbound_comms.md) — outbound drafts (email/comment) rendered from templates.
  - Key files: `outbound_comms/models.py`, `outbound_comms/views.py`, `outbound_comms/services.py`,
    `outbound_comms/urls.py`
  - Depends on: `identity`, `work_items`, `templates`, `collaboration`, `notifications`, `realtime`,
    `audit`
- [`customization`](customization.md) — saved views + custom fields/values.
  - Key files: `customization/models.py`, `customization/views.py`, `customization/services.py`,
    `customization/urls.py`
  - Depends on: `identity`, `work_items`, `audit`
- [`realtime`](realtime.md) — websocket routing + org-scoped publish helper.
  - Key files: `viarah/asgi.py`, `realtime/routing.py`, `realtime/consumers.py`,
    `realtime/services.py`, `viarah/settings/base.py`
  - Depends on: `identity` (membership gating), Redis channel layer
- [`core`](core.md) — non-API endpoints (`/healthz`, PWA smoke page) + Liquid helper.
  - Key files: `core/views.py`, `core/urls.py`, `core/liquid.py`
  - Depends on: DB connection (health checks)
- [`push`](push.md) — Web Push subscriptions + delivery task.
  - Key files: `push/models.py`, `push/views.py`, `push/services.py`, `push/tasks.py`, `push/urls.py`
  - Depends on: `notifications` (event emissions), VAPID env vars
- [`integrations`](integrations.md) — GitLab integration config, links, webhooks, metadata refresh.
  - Key files: `integrations/models.py`, `integrations/views.py`, `integrations/services.py`,
    `integrations/gitlab.py`, `integrations/tasks.py`, `integrations/urls.py`
  - Depends on: `identity`, `work_items`, `audit`, Celery

## Frontend

- [`frontend`](../frontend.md) — Vue SPA under `frontend/` (canonical run steps in
  [`frontend/README.md`](../../frontend/README.md)).
