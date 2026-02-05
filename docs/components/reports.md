# reports

Reports are generated from templates and a scoped project context. The system stores HTML output and
optionally renders PDFs via a Node + Chromium renderer.

## Key entrypoints

- `reports/models.py` — `ReportRun`, `ReportRunPdfRenderLog`
- `reports/services.py` — scope normalization + context building + HTML rendering
- `reports/views.py`, `reports/urls.py` — REST API
- `reports/tasks.py` — PDF render task (`render_report_run_pdf`)
- `reports/pdf_renderer/render.js` — Node renderer invoked by the Celery task

## Models

- `ReportRun` — org/project/template run; stores rendered output and optional PDF artifact metadata
- `ReportRunPdfRenderLog` — status + QA report for PDF render attempts

## API routes

Mounted under `/api/`:

- `/api/orgs/<org_id>/report-runs` → `reports.views.report_runs_collection_view`
- `/api/orgs/<org_id>/report-runs/<report_run_id>` → `reports.views.report_run_detail_view`
- `/api/orgs/<org_id>/report-runs/<report_run_id>/regenerate` → `reports.views.report_run_regenerate_view`
- `/api/orgs/<org_id>/report-runs/<report_run_id>/web-view` → `reports.views.report_run_web_view`
- `/api/orgs/<org_id>/report-runs/<report_run_id>/pdf` → `reports.views.report_run_pdf_view`
- `/api/orgs/<org_id>/report-runs/<report_run_id>/render-logs` → `reports.views.report_run_pdf_render_logs_view`

The canonical contract is `docs/api/openapi.yaml` + `docs/api/scope-map.yaml`.

## Background jobs / tasks

- `reports.tasks.render_report_run_pdf()` renders a PDF for a given `ReportRunPdfRenderLog` by
  invoking `node reports/pdf_renderer/render.js` with a Chromium binary.
- Optional PDF env vars are documented in `.env.example`:
  - `VIA_RAH_PDF_CHROME_BIN`
  - `VIA_RAH_PDF_NO_SANDBOX`
  - `VIA_RAH_PDF_RENDER_TIMEOUT_SECONDS`

## Interactions / dependencies

- Depends on `templates` (`TemplateType.REPORT`) and `work_items.Project` for scope/context.
- Share links for reports (and “report published” notifications) are handled by `share_links`.
