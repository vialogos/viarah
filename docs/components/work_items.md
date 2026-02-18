# work_items

Work items are the core PM data model: projects contain epics, epics contain tasks, and tasks
contain subtasks.

## Key entrypoints

- `work_items/models.py` — `Project`, `Epic`, `Task`, `Subtask`, `WorkItemStatus`
- `work_items/views.py` — REST endpoints + access control + side effects (audit/notifications/realtime)
- `work_items/urls.py` — route map (mounted under `/api/`)
- `work_items/progress.py` — progress rollups and workflow-stage progress context

## Models

- `Project` — org-scoped container; optionally linked to a `workflows.Workflow`
- `Epic` — project grouping
- `Task` — primary unit of work (`assignee_user`, date range, legacy `status`, `client_safe`, optional
  `workflow_stage`).
- `Subtask` — task child; can reference a `workflows.WorkflowStage` via `workflow_stage`

## API routes

Mounted under `/api/`:

- `/api/orgs/<org_id>/projects` → `work_items.views.projects_collection_view`
- `/api/orgs/<org_id>/projects/<project_id>` → `work_items.views.project_detail_view`
- `/api/orgs/<org_id>/projects/<project_id>/epics` → `work_items.views.project_epics_collection_view`
- `/api/orgs/<org_id>/epics/<epic_id>` → `work_items.views.epic_detail_view`
- `/api/orgs/<org_id>/epics/<epic_id>/tasks` → `work_items.views.epic_tasks_collection_view`
- `/api/orgs/<org_id>/projects/<project_id>/tasks` → `work_items.views.project_tasks_list_view`
- `/api/orgs/<org_id>/tasks/<task_id>` → `work_items.views.task_detail_view`
- `/api/orgs/<org_id>/tasks/<task_id>/subtasks` → `work_items.views.task_subtasks_collection_view`
- `/api/orgs/<org_id>/subtasks/<subtask_id>` → `work_items.views.subtask_detail_view`

Method-by-method request/response schemas live in `docs/api/openapi.yaml`.

## Projects (API/CLI examples)

These examples use placeholders (do not paste secrets into docs):

```bash
BASE_URL="http://localhost:8000"
ORG_ID="<org_id>"
PROJECT_ID="<project_id>"
WORKFLOW_ID="<workflow_id>"
TOKEN="<token>"
```

List projects:

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/orgs/$ORG_ID/projects"
```

Create project (name required; description optional):

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"New project","description":"Optional description"}' \
  "$BASE_URL/api/orgs/$ORG_ID/projects"
```

Update project name/description:

```bash
curl -fsS -X PATCH \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Renamed project","description":"Updated description"}' \
  "$BASE_URL/api/orgs/$ORG_ID/projects/$PROJECT_ID"
```

Assign/update workflow:

```bash
curl -fsS -X PATCH \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"workflow_id\":\"$WORKFLOW_ID\"}" \
  "$BASE_URL/api/orgs/$ORG_ID/projects/$PROJECT_ID"
```

Unassign workflow:

```bash
curl -fsS -X PATCH \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"workflow_id":null}' \
  "$BASE_URL/api/orgs/$ORG_ID/projects/$PROJECT_ID"
```

Delete project:

```bash
curl -fsS -X DELETE -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/orgs/$ORG_ID/projects/$PROJECT_ID"
```

Notes:

- Project-restricted API keys cannot create new projects (POST is forbidden).
- Workflow changes can be rejected when tasks/subtasks have `workflow_stage_id` set.

## Workflow stages, status, and progress

When a project has a workflow assigned, tasks and subtasks can be staged into workflow stages.

- `workflow_stage_id` is the source of truth for the current stage/bucket when it is non-null.
- The legacy `status` field is derived from `WorkflowStage.category` when a work item is staged.
  Direct `status` writes are rejected while `workflow_stage_id` is set.
- Progress is policy-driven (resolved Project default → Epic override → Task override):
  - `subtasks_rollup`: task/epic progress is the average of subtask progress
  - `workflow_stage`: task progress comes from the staged workflow stage `progress_percent`
  - `manual`: task/epic progress comes from `manual_progress_percent`

## Auth / access control

- Supports session auth and API keys (see `_require_org_access()` in `work_items/views.py`).
- API keys can be restricted to a single project via `ApiKey.project_id`; many handlers enforce this
  (see `_principal_project_id()` checks).

Client visibility:

- Some work items are marked `client_safe` (notably `Task.client_safe`).
- When an org membership role is `client`, list/detail responses use client-safe payload shapes and
  may hide non-client-safe rows (see `*_client_safe_dict()` helpers in `work_items/views.py`).

## Side effects (notifications + realtime)

`work_items/views.py` emits events when key fields change:

- Notifications via `notifications.services.emit_project_event()` /
  `notifications.services.emit_assignment_changed()`
- Websocket events via `realtime.services.publish_org_event()`

## Interactions / dependencies

- References workflows (`Project.workflow`, `Subtask.workflow_stage`) and uses workflow progress
  helpers in `work_items/progress.py`.
- Includes custom field data by joining `customization.CustomFieldDefinition` and
  `customization.CustomFieldValue`.
- Collaboration (comments/attachments) uses task/epic IDs as its targets.
