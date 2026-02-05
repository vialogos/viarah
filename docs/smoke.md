# Docs smoke checklist

Run this after changing repo docs (`README.md` or anything under `docs/`).

## Setup

- Install dev deps (if needed for local runs): `python3 -m pip install -r requirements-dev.txt`.

## Automated checks

From the repo root:

```bash
ruff check .
ruff format --check .
python3 manage.py test
```

Notes:

- `manage.py` loads `.env` (via `python-dotenv`). If you want to run tests without Docker Compose,
  you can override the required env vars on the command line, for example:

```bash
DJANGO_SECRET_KEY=dev DATABASE_URL=sqlite:////tmp/viarah-test.sqlite3 CELERY_BROKER_URL=redis://localhost:6379/0 python3 manage.py test
```

- Compose alternative:

```bash
docker compose up -d
docker compose exec web python manage.py test
```

## Manual doc navigation checks

- `README.md` → `docs/index.md` link works.
- `docs/index.md` → `docs/components/index.md` link works.
- `docs/components/index.md` links to every component page.
- Existing docs links still work:
  - `docs/operator-basics.md`
  - `docs/api/*`
  - `docs/web-push.md`

## Wiki link hub check

The GitLab Wiki Home page should be link-first and point to the canonical repo docs (README +
`docs/index.md` + component inventory).

- Wiki updates are tracked separately (see `vialogos-labs/viarah#31`).
