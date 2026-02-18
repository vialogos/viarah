# Dashboard metrics (v1)

This document defines the internal dashboard’s metrics in terms of ViaRah API queries plus deterministic client-side
filters/sorts.

## Scope (required)

All dashboard data is scoped to the currently selected org/project context:
- `org_id = <org_id>`
- `project_id = <project_id>`

Dashboard v1 does not support “All orgs” / “All projects” aggregation mode.

## Source query

Dashboard v1 uses the unfiltered task list as the source of truth:

```text
GET /api/orgs/<org_id>/projects/<project_id>/tasks
```

(The API also supports `?status=backlog|in_progress|qa|done`, but the dashboard computes all metrics from the single
unfiltered response.)

## Metrics

### Status counts (Backlog / In progress / QA / Done)

Client-side definition:
- Group tasks by `task.status`.
- Count tasks where `task.status` equals:
  - `backlog`
  - `in_progress`
  - `qa`
  - `done`

### Overdue

Client-side definition:
- A task is overdue when:
  - `task.end_date` is non-null, and
  - `task.end_date < <today_utc_date>` (string compare on `YYYY-MM-DD`), and
  - `task.status != done`

Where:
- `<today_utc_date>` is computed as `new Date().toISOString().slice(0, 10)`.

### Recent updates

Client-side definition:
- Filter tasks where `task.updated_at` is present.
- Sort by `updated_at` descending (most recent first).
- Display the top 10.

