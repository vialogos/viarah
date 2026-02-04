# ViaRah docs

This is the canonical documentation map for the ViaRah repo.

## Start here

- Onboarding + local quickstarts: [`README.md`](../README.md)
- Frontend overview: [`docs/frontend.md`](frontend.md) (canonical run steps live in
  [`frontend/README.md`](../frontend/README.md))
- Component inventory (backend + frontend): [`docs/components/index.md`](components/index.md)
- API contract artifacts: [`docs/api/README.md`](api/README.md)
- Operator/self-hosting notes: [`docs/operator-basics.md`](operator-basics.md)
- Docs smoke checklist: [`docs/smoke.md`](smoke.md)

## Architecture at a glance

- Backend: Django + ASGI (`viarah/asgi.py`) served by `daphne`.
- REST API: mounted under `/api/` (`viarah/urls.py`) with per-app routes in `<app>/urls.py`.
- Realtime: Django Channels websockets (`realtime/routing.py`, `realtime/consumers.py`) backed by a
  Redis channel layer (`CHANNEL_LAYERS` in `viarah/settings/base.py`).
- Background jobs: Celery (`viarah/celery.py`) using a Redis broker (`CELERY_BROKER_URL`).
- Frontend: Vue 3 SPA under `frontend/` (Vite dev server proxies `/api/*`).

## Key code entrypoints

- Settings / env vars: `viarah/settings/base.py`, `.env.example`
- URL routing: `viarah/urls.py`
- ASGI routing: `viarah/asgi.py`, `realtime/routing.py`
- Celery app: `viarah/celery.py`
- Health check: `core/views.py` (`GET /healthz`)
- API contract: `docs/api/openapi.yaml` + `docs/api/scope-map.yaml`

## Where to look by topic

- Auth (session + API key): [`docs/components/identity.md`](components/identity.md),
  [`docs/components/api_keys.md`](components/api_keys.md), [`docs/api/auth.md`](api/auth.md)
- Work tracking (projects/epics/tasks): [`docs/components/work_items.md`](components/work_items.md)
- Workflows/stages: [`docs/components/workflows.md`](components/workflows.md)
- Comments/attachments: [`docs/components/collaboration.md`](components/collaboration.md)
- Templates (Liquid): [`docs/components/templates.md`](components/templates.md),
  [`docs/components/core.md`](components/core.md)
- Reports + share links: [`docs/components/reports.md`](components/reports.md),
  [`docs/components/share_links.md`](components/share_links.md)
- SoWs: [`docs/components/sows.md`](components/sows.md)
- Notifications (in-app/email/push): [`docs/components/notifications.md`](components/notifications.md),
  [`docs/components/push.md`](components/push.md), [`docs/web-push.md`](web-push.md)
- GitLab integration: [`docs/components/integrations.md`](components/integrations.md)
- Custom fields + saved views: [`docs/components/customization.md`](components/customization.md)
- Realtime/websockets: [`docs/components/realtime.md`](components/realtime.md)
