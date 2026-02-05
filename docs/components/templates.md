# templates

Templates are Liquid-based documents with versioning. They back reports, outbound email/comment
drafts, and SoWs.

## Key entrypoints

- `templates/models.py` — `Template`, `TemplateVersion`, `TemplateType`
- `templates/services.py` — create + validate templates/versions
- `templates/views.py`, `templates/urls.py` — REST API
- `core/liquid.py` — Liquid parsing + allowed filter set

## Models

- `Template` (org-scoped; `type` is one of `report`, `email`, `comment`, `sow`)
- `TemplateVersion` (incrementing `version`, stores `body`)

## API routes

Mounted under `/api/`:

- `/api/orgs/<org_id>/templates` → `templates.views.templates_collection_view`
- `/api/orgs/<org_id>/templates/<template_id>` → `templates.views.template_detail_view`
- `/api/orgs/<org_id>/templates/<template_id>/versions` → `templates.views.template_versions_collection_view`
- `/api/orgs/<org_id>/templates/<template_id>/versions/<version_id>` → `templates.views.template_version_detail_view`

The canonical contract is `docs/api/openapi.yaml` + `docs/api/scope-map.yaml`.

## Validation rules

`templates.services.validate_template_body()` enforces:

- body is non-empty and below `MAX_TEMPLATE_BODY_CHARS`
- body parses as a Liquid template (`core.liquid.validate_liquid_template()`)

## Interactions / dependencies

- Used by `reports` (report template bodies), `outbound_comms` (email/comment drafts), and `sows`.
- Writes audit events via `audit.services.write_audit_event` for create/version events.
