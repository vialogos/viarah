# sows

SoWs (Statements of Work) are versioned, signer-gated documents rendered from templates and stored
with optional PDF artifacts.

## Key entrypoints

- `sows/models.py` — `SoW`, `SoWVersion`, `SoWSigner`, `SoWPdfArtifact`
- `sows/services.py` — create/version/send/respond helpers
- `sows/views.py`, `sows/urls.py` — REST API
- `sows/tasks.py` — PDF render task (`render_sow_version_pdf`)

## Models

- `SoW` — org/project SoW, points at a `templates.Template`
- `SoWVersion` — versioned body (`body_markdown` + `body_html`) with status (`draft`, `pending_signature`, …)
- `SoWSigner` — per-user signer decision row
- `SoWPdfArtifact` — PDF render status + artifact metadata

## API routes

Mounted under `/api/`:

- `/api/orgs/<org_id>/sows` → `sows.views.sows_collection_view`
- `/api/orgs/<org_id>/sows/<sow_id>` → `sows.views.sow_detail_view`
- `/api/orgs/<org_id>/sows/<sow_id>/send` → `sows.views.sow_send_view`
- `/api/orgs/<org_id>/sows/<sow_id>/respond` → `sows.views.sow_respond_view`
- `/api/orgs/<org_id>/sows/<sow_id>/versions` → `sows.views.sow_versions_collection_view`
- `/api/orgs/<org_id>/sows/<sow_id>/pdf` → `sows.views.sow_pdf_view`

The canonical contract is `docs/api/openapi.yaml` + `docs/api/scope-map.yaml`.

## Auth / access control

SoW endpoints require a session user and explicitly forbid API keys (see `_require_session_user()`
in `sows/views.py`).

## Background jobs / tasks

- `sows.tasks.render_sow_version_pdf()` renders a PDF for a `SoWPdfArtifact` using the shared Node +
  Chromium renderer under `reports/pdf_renderer/`.

## Interactions / dependencies

- Depends on `templates` (`TemplateType.SOW`) and `work_items.Project`.
- Uses shared PDF renderer assets from `reports/` (see `.env.example` for PDF env vars).
