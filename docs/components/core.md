# core

Core owns a small set of non-API endpoints and shared helpers used by other components.

## Key entrypoints

- `core/urls.py`, `core/views.py` — non-API endpoints (`/healthz`, service worker, manifest)
- `core/liquid.py` — Liquid template validation + allowed filter set

## Routes

Mounted at the root (not under `/api/`):

- `/` → `core.views.index` (Web Push / PWA v1 smoke page)
- `/manifest.webmanifest` → `core.views.manifest_webmanifest`
- `/service-worker.js` → `core.views.service_worker_js`
- `/healthz` → `core.views.healthz` (DB connectivity gate)

## Liquid helper

`core.liquid` provides:

- `validate_liquid_template()` — parse-only validation used by `templates.services`
- `liquid_environment()` — a shared `liquid.Environment` with a restricted filter allowlist

## Interactions / dependencies

- Templates are validated using `core.liquid.validate_liquid_template()`.
- `/healthz` uses the default DB connection and returns `503` when DB connectivity fails.
