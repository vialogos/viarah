# workflows

Workflows define the stages a project moves through (including metadata like “done”, “QA”, and
“counts as WIP”).

## Key entrypoints

- `workflows/models.py` — `Workflow`, `WorkflowStage`
- `workflows/views.py` — handlers + stage ordering/normalization logic
- `workflows/urls.py` — route map (mounted under `/api/`)
- `work_items/models.py` — `Project.workflow`, `Subtask.workflow_stage` consumers

## Models

- `Workflow` — org-scoped workflow definition
- `WorkflowStage` — ordered stages within a workflow (`is_done`, `is_qa`, `counts_as_wip`)

## API routes

Mounted under `/api/`:

- `/api/orgs/<org_id>/workflows` → `workflows.views.workflows_collection_view`
- `/api/orgs/<org_id>/workflows/<workflow_id>` → `workflows.views.workflow_detail_view`
- `/api/orgs/<org_id>/workflows/<workflow_id>/stages` → `workflows.views.workflow_stages_collection_view`
- `/api/orgs/<org_id>/workflows/<workflow_id>/stages/<stage_id>` → `workflows.views.workflow_stage_detail_view`

The canonical contract is `docs/api/openapi.yaml` + `docs/api/scope-map.yaml`.

## Auth / access control

- Supports both session auth and API keys.
- Read access:
  - session user must be an org member
  - API key principal must match org and include `read` (or `write`) scope
- Write access:
  - session user must have org role `admin` or `pm`
  - API key principal must include `write` scope

See `_require_read_access()` / `_require_write_access()` in `workflows/views.py`.

## Notable constraints

- A workflow must have exactly one `is_done=true` stage (enforced by a conditional unique
  constraint).
- Stage orders are normalized to a contiguous 1..N sequence; stage move logic uses temporary order
  values to avoid unique collisions (see `_apply_stage_orders()` in `workflows/views.py`).

## Interactions / dependencies

- Writes audit events via `audit.services.write_audit_event`.
- Work items use workflow stages for progress and stage assignment (`work_items/progress.py`).
