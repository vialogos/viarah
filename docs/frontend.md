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
  - Internal roles (`admin`/`pm`/`member`) can create subtasks.
  - Ownership assignment (`assignee_user_id`):
    - Admin/PM: assignee dropdown from org memberships.
    - Member: assign-to-me / unassign only.
- Client-only users are routed under `/client/*` and cannot access internal `/work/*` routes (see `frontend/src/routerGuards.ts`).

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
