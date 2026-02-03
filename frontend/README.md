# ViaRah frontend

Minimal Vue 3 SPA scaffold for PM workflows.

## Local development

Prereqs: backend running on `http://localhost:8000`.

Ensure your backend `.env` includes:

```
CSRF_TRUSTED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Then:

```bash
npm install
npm run dev
```

Vite proxies `/api/*` to the backend.

## Scripts

- `npm run dev`
- `npm run build`
- `npm run preview`
- `npm run lint`
- `npm run typecheck`
- `npm test`
