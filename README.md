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
- `DATABASE_URL`: Postgres DSN (used by Django)
- `CELERY_BROKER_URL`: Redis URL (used by Celery)
- `CELERY_HEARTBEAT_SECONDS` (optional): worker heartbeat interval (seconds)

## Endpoints

- `GET /healthz`: returns `200` only when DB connectivity succeeds; otherwise `503` with a minimal response body.
