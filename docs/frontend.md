# Frontend (Vue SPA)

The frontend lives in `frontend/` and is a minimal Vue 3 SPA scaffold. The canonical run
instructions are in [`frontend/README.md`](../frontend/README.md).

## Key entrypoints

- `frontend/src/main.ts` — app bootstrap (Vue + Pinia + router)
- `frontend/src/router.ts` — route map + auth guards (client vs internal roles)
- `frontend/src/routerGuards.ts` — pure guard helpers used by router + tests
- `frontend/src/App.vue` — root route outlet
- `frontend/src/layouts/AppShell.vue` — internal app shell (sidebar + utility bar)
- `frontend/src/layouts/appShellNav.ts` — deterministic sidebar/settings/quick-action model
- `frontend/src/stores/session.ts` — session bootstrap (`/api/me`) and auth state

## Work authoring UI

- Work list: `frontend/src/pages/WorkListPage.vue`
  - Internal roles (`admin`/`pm`/`member`) can create epics and add tasks when org+project context is selected.
- Work detail: `frontend/src/pages/WorkDetailPage.vue`
  - Internal roles (`admin`/`pm`/`member`) can create subtasks and update ownership assignment when org+project context is selected.
  - Ownership assignment (`assignee_user_id`):
    - Admin/PM: assignee dropdown from org memberships.
    - Member: assign-to-me / unassign only.
- Client-only users are routed under `/client/*` and cannot access internal `/work/*` routes (see `frontend/src/routerGuards.ts`).

## Schedule views (Timeline + Gantt)

- Timeline roadmap: `frontend/src/pages/TimelinePage.vue`
  - Renders an interactive roadmap at `/timeline` using `vis-timeline` (Day/Week/Month time axis presets, grouping, search/filtering, details panel).
  - RBAC constraints:
    - Client portal (`/client/timeline`) must not request internal-only endpoints (epics, task gitlab-links).
    - Internal users can group by Epic and can view GitLab links in the details panel when permitted.
  - Temporary rollback safety: legacy list rendering is available via `?view=list` (one release cycle).
  - Implementation helpers:
    - Timeline wrapper component: `frontend/src/components/VlTimelineRoadmap.vue`
    - Pure mapping helpers + tests: `frontend/src/utils/timelineRoadmap.ts`
- Gantt: `frontend/src/pages/GanttPage.vue`
  - Simple bar visualization over a computed window (no third-party gantt lib).

## Global context scope (read-only)

Internal (non-client-only) users can switch the org/project context selector into aggregate modes:

- **All orgs**: aggregate across all org memberships where the role is internal (`admin`/`pm`/`member`).
- **All projects**: aggregate across all projects in a selected org.

In either aggregate mode, internal work surfaces are **read-only**:

- `/work` and `/dashboard` show combined lists with explicit org + project labels on each work item.
- Any mutating action is disabled/hidden until a specific org + project is selected.

Implementation notes:

- v1 uses client-side fan-out over existing APIs (`/api/me`, `/api/orgs/:orgId/projects`, `/api/orgs/:orgId/projects/:projectId/tasks`, and epics where available).
- To avoid request storms, fan-out uses a bounded concurrency pool and reports partial failures in the UI with org/project attribution.
- Aggregate work list links include `orgId` / `projectId` query params so `WorkDetailPage` can fetch the task in read-only mode even when the selector is not in a concrete scope.

## PatternFly (vue-patternfly)

- Prefer PatternFly Vue components (`@vue-patternfly/core` + `@vue-patternfly/table`) for UI primitives.
- Semantic tags/labels must use `frontend/src/components/VlLabel.vue` (do not use chips/badges for status/progress labels).
- Any tabular data should use `<pf-table>`.
- Coverage matrix and guard-rail grep proofs live in `docs/patternfly-vue-component-inventory.md`.

## Dev workflow

From `frontend/`:

```bash
npm install
npm run dev
```

Notes:

- Vite proxies `/api/*` to the backend so the SPA can call Django endpoints during local dev.
- When using session cookies, ensure the backend’s `CSRF_TRUSTED_ORIGINS` includes the Vite dev
  origin (see `.env.example`).

## Scripts

See `frontend/package.json` for the full list; common ones include:

- `npm run dev`
- `npm run build`
- `npm run preview`
- `npm run lint`
- `npm run typecheck`
- `npm test`
