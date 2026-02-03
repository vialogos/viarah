# ViaRah backend (bootstrap)

Minimal Django + Postgres + Celery worker baseline for ViaRah.

## Local quickstart (Docker Compose)

Prereqs: Docker + Docker Compose plugin.

```bash
cp .env.example .env
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py test
docker compose exec web python manage.py makemigrations --check --dry-run
curl -fsS http://localhost:8000/healthz
```

## Frontend quickstart (Vite + Vue)

Prereqs: Node.js + npm.

```bash
cd frontend
npm install
npm run dev
```

Notes:
- The frontend expects the backend running on `http://localhost:8000`.
- For session+CSRF auth from the Vite origin (`http://localhost:5173`), ensure your `.env` includes
  `CSRF_TRUSTED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`.

To validate the unhealthy case:

```bash
docker compose stop db
curl -f http://localhost:8000/healthz || true
docker compose start db
```

Worker logs should include a ready/heartbeat signal:

```bash
docker compose logs --no-color --tail=200 worker
```

## Environment variables

All are required unless noted.

- `DJANGO_SETTINGS_MODULE`: settings module (default `viarah.settings.dev`)
- `DJANGO_DEBUG`: `1/0` (default `1` in `.env.example`)
- `DJANGO_SECRET_KEY`: Django secret key (use a dev-only value locally)
- `ALLOWED_HOSTS`: comma-separated hosts
- `CSRF_TRUSTED_ORIGINS` (optional): comma-separated origins allowed to make CSRF-protected requests
- `DATABASE_URL`: Postgres DSN (used by Django)
- `CELERY_BROKER_URL`: Redis URL (used by Celery)
- `CELERY_HEARTBEAT_SECONDS` (optional): worker heartbeat interval (seconds)

## Operator basics (self-hosting)

See [`docs/operator-basics.md`](docs/operator-basics.md) for:
- Postgres backup/restore commands (Docker Compose volume `db_data`)
- Upgrade steps between git refs/tags (including migrations)
- Environment variable catalog (placeholders only; no secrets)
- Operator smoke checklist

## Endpoints

- `GET /healthz`: returns `200` only when DB connectivity succeeds; otherwise `503` with a minimal response body.
