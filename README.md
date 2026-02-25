# ViaRah

Django backend + Vue SPA for PM workflows (work items, templates, reports, and client share links).

## Docs (start here)

- [`docs/index.md`](docs/index.md) — canonical docs map
- [`docs/components/index.md`](docs/components/index.md) — component inventory (per `INSTALLED_APPS`)
- [`docs/frontend.md`](docs/frontend.md) — frontend overview (links to `frontend/README.md`)
- [`docs/api/README.md`](docs/api/README.md) — API contract artifacts (`openapi.yaml` + `scope-map.yaml`)
- [`docs/operator-basics.md`](docs/operator-basics.md) — self-hosting/operator notes
- [`docs/smoke.md`](docs/smoke.md) — docs smoke checklist

## Local quickstart (backend, Docker Compose)

Prereqs: Docker + Docker Compose plugin.

```bash
cp .env.example .env
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py test
curl -fsS http://localhost:8000/healthz
```

Optional sanity checks:

```bash
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose logs --no-color --tail=200 worker
```

To validate the unhealthy case:

```bash
docker compose stop db
curl -f http://localhost:8000/healthz || true
docker compose start db
```

## Bootstrap (first org + PM + project + API key)

ViaRah currently has no UI/API to create the *first* org. After you’ve run migrations, use the
idempotent bootstrap command:

```bash
docker compose exec web python manage.py bootstrap_v1 \
  --org-name "Org" \
  --pm-email "pm@example.com" \
  --project-name "Project" \
  --api-key-name "Bootstrap key"
```

Notes:
- If the PM user does not exist, you’ll be prompted for a password (input hidden). Avoid passing
  `--pm-password` unless you understand the shell history/process-list risks.
- By default, the command **does not print** API key tokens. To emit the one-time token, pass
  `--reveal` (store it immediately; it cannot be retrieved later). For file-based handling, use
  `--write-token-file <path>` (creates the file with mode `0600`).
- The command is safe to re-run with the same inputs (create-or-reuse). If name-based matching is
  ambiguous (multiple rows), it fails with a clear error and does not create additional rows.

Verify an emitted token (see [`docs/api/auth.md`](docs/api/auth.md)):

```bash
curl -fsS -H "Authorization: Bearer <TOKEN>" http://localhost:8000/api/me
```

## Frontend quickstart (Vite + Vue)

Prereqs: Node.js + npm (or equivalent).

```bash
cd frontend
npm install
npm run dev
```

Notes:
- The frontend expects the backend running on `http://localhost:8000`.
- Vite proxies `/api/*` to the backend (see `frontend/vite.config.ts`).
- For session + CSRF auth from the Vite origin (`http://localhost:5173`), ensure your backend `.env`
  includes: `CSRF_TRUSTED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`.

## Common dev commands

From the repo root (after installing dev deps via `python3 -m pip install -r requirements-dev.txt`):

```bash
ruff check .
ruff format --check .
python3 manage.py test
python3 manage.py makemigrations --check --dry-run
python3 scripts/api_completeness_check.py
```

Non-Compose unit tests (sqlite):

```bash
DJANGO_SECRET_KEY=dev DATABASE_URL=sqlite:////tmp/viarah-test.sqlite3 CELERY_BROKER_URL=redis://localhost:6379/0 python3 manage.py test
```

Notes:
- The non-Compose path is intended for quick unit-test runs and still requires required env vars.
  If you don’t have Redis locally, prefer the Docker Compose workflow.

## Environment variables

All are required unless noted. For local defaults, see `.env.example` (copy to `.env`, do not
commit).

- `DJANGO_SETTINGS_MODULE` (default: `viarah.settings.dev`)
- `DJANGO_DEBUG` (default: `1` in `.env.example`)
- `DJANGO_SECRET_KEY`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS` (optional)
- `DATABASE_URL`
- `CELERY_BROKER_URL`
- `CELERY_HEARTBEAT_SECONDS` (optional)

Web Push / PWA (optional):
- `WEBPUSH_VAPID_PUBLIC_KEY`
- `WEBPUSH_VAPID_PRIVATE_KEY`
- `WEBPUSH_VAPID_SUBJECT`

SMTP (optional; used by notifications):
- `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`,
  `DEFAULT_FROM_EMAIL`

PDF rendering (optional; used by reports/SoWs):
- `VIA_RAH_PDF_CHROME_BIN`
- `VIA_RAH_PDF_NO_SANDBOX`
- `VIA_RAH_PDF_RENDER_TIMEOUT_SECONDS`

GitLab integrations (optional):
- `VIA_RAH_ENCRYPTION_KEY`
- `GITLAB_METADATA_TTL_SECONDS`

## Operator basics (self-hosting)

See [`docs/operator-basics.md`](docs/operator-basics.md) for backups, upgrades, and operator smoke
checks.

Web Push docs: [`docs/web-push.md`](docs/web-push.md)

## Key endpoints

- `GET /healthz` — returns `200` only when DB connectivity succeeds; otherwise `503`.
- Websocket: `/ws/orgs/<org_id>/events` (see [`docs/components/realtime.md`](docs/components/realtime.md)).
