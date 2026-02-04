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
- `Task` — primary unit of work (`assignee_user`, date range, `status`, `client_safe`)
- `Subtask` — task child; can reference a `workflows.WorkflowStage`

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
