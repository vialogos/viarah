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
