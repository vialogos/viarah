# customization

Customization provides per-user saved views and per-project custom fields/values (including
client-safe filtering).

## Key entrypoints

- `customization/models.py` — `SavedView`, `CustomFieldDefinition`, `CustomFieldValue`
- `customization/services.py` — normalization + validation helpers
- `customization/views.py`, `customization/urls.py` — REST API

## Models

- `SavedView` — per-user saved filters/sort/group-by config (optionally `client_safe`)
- `CustomFieldDefinition` — per-project custom field schema (`field_type`, options, `client_safe`)
- `CustomFieldValue` — per-work-item value row (`work_item_type` + `work_item_id`)

## API routes

Mounted under `/api/`:

- `/api/orgs/<org_id>/projects/<project_id>/saved-views` → `customization.views.saved_views_collection_view`
- `/api/orgs/<org_id>/saved-views/<saved_view_id>` → `customization.views.saved_view_detail_view`
- `/api/orgs/<org_id>/projects/<project_id>/custom-fields` → `customization.views.custom_fields_collection_view`
- `/api/orgs/<org_id>/custom-fields/<field_id>` → `customization.views.custom_field_detail_view`
- `/api/orgs/<org_id>/tasks/<task_id>/custom-field-values` → `customization.views.task_custom_field_values_view`
- `/api/orgs/<org_id>/subtasks/<subtask_id>/custom-field-values` → `customization.views.subtask_custom_field_values_view`

The canonical contract is `docs/api/openapi.yaml` + `docs/api/scope-map.yaml`.

## Auth / access control

Customization endpoints require a session user.

Client visibility:

- `client` role members can read saved views and custom fields, but listing endpoints filter down to
  `client_safe=true` rows where applicable (see `customization/views.py`).

## Interactions / dependencies

- Work item APIs join custom fields/values when returning project/task/subtask payloads (see
  `work_items/views.py`).
- Writes audit events via `audit.services.write_audit_event` for create/update/archive actions.
