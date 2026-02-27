# Operator basics (self-hosting)

This document is for operators running ViaRah via the repo’s Docker Compose stack.

It focuses on the basics you need to operate safely:
- Back up and restore the Postgres database used by the Compose stack.
- Upgrade between git refs/tags (including running Django migrations).
- Know which environment variables exist (placeholders only; no secrets).
- Run a smoke checklist to validate the stack after changes.

## Assumptions

- You are operating from the repo root (the directory containing `docker-compose.yml`).
- You are using Docker + Docker Compose plugin (`docker compose ...`).
- The Compose stack uses:
  - Postgres service `db` with a named volume `db_data` for persistence.
  - Django service `web`.
  - Celery worker service `worker` using Redis as broker (`redis`).

## Installer/doctor (first org + platform admin + PM + project + API key)

ViaRah currently has no supported UI/API to create the *first* org. Use the idempotent
`bootstrap_v1` management command after migrations are applied.

The command includes:
- **Doctor mode** (`--doctor`): validates runtime dependencies and key operator configuration.
- **Optional platform admin creation**: creates/reuses a Django superuser that ViaRah treats as a
  platform-admin (cross-org) user.

### Doctor (validate config before install)

```bash
docker compose exec web python manage.py bootstrap_v1 --doctor
```

If the doctor fails:
- Ensure Postgres + Redis are reachable from the `web` container.
- Ensure `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, and `CSRF_TRUSTED_ORIGINS` are configured for your
  deployment.
- Ensure `PUBLIC_APP_URL` is set so invite + password reset links are environment-correct.

### Bootstrap (create first org + users + project)

Example (includes a root platform admin):

```bash
docker compose exec web python manage.py migrate

docker compose exec web python manage.py bootstrap_v1 \
  --platform-admin-email "admin@example.com" \
  --org-name "Org" \
  --pm-email "pm@example.com" \
  --project-name "Project" \
  --api-key-name "Bootstrap key"
```

Notes:
- If the PM user does not exist, you’ll be prompted for a password (input hidden). Avoid passing
  `--pm-password` unless you understand the shell history/process-list risks.
- If `--platform-admin-email` is provided and the user does not exist, you’ll be prompted for a
  password (input hidden). If the user exists, the command ensures it is a superuser/staff/active
  account.
- The command is safe to re-run with the same inputs (create-or-reuse). If name-based matching is
  ambiguous (multiple rows), it fails with a clear error and does not create additional rows.

### API key token handling (secret hygiene)

- By default, the command **does not print** API key tokens.
- To emit a one-time token to stdout, pass `--reveal` (store it immediately; it cannot be retrieved
  later).
- To write the one-time token to a file with restrictive permissions, pass
  `--write-token-file <path>` (creates the file with mode `0600`).

Compose note: `--write-token-file` writes inside the container filesystem. Copy it out to the host
and delete it when done:

```bash
docker compose exec web python manage.py bootstrap_v1 \
  --org-name "Org" \
  --pm-email "pm@example.com" \
  --project-name "Project" \
  --api-key-name "Bootstrap key" \
  --write-token-file /tmp/viarah_bootstrap_token.json

WEB_CID="$(docker compose ps -q web)"
docker cp "$WEB_CID:/tmp/viarah_bootstrap_token.json" ./viarah_bootstrap_token.json
chmod 600 ./viarah_bootstrap_token.json
```

To verify an emitted token (see `docs/api/auth.md`):

```bash
curl -fsS -H "Authorization: Bearer <TOKEN>" http://localhost:8000/api/me
```

If you need a new token later, rotate the API key via the API (secrets are shown only at rotate
time) or create a new key with a distinct name.

## Backup and restore (Postgres)

### Where the data lives

The Postgres data directory is persisted via a named Docker volume:
- Compose volume: `db_data`
- Mount path in the `db` container: `/var/lib/postgresql/data`

Important:
- `docker compose down` does **not** remove named volumes by default.
- `docker compose down -v` **does** remove named volumes (including `db_data`) and will wipe the database.

To see the actual Docker volume name created by Compose:

```bash
docker volume ls | grep db_data
docker volume inspect <the-volume-name>
```

### Backup (logical dump)

This writes a SQL dump file to the host filesystem:

```bash
BACKUP_FILE="/tmp/viarah_backup_$(date -u +%Y%m%dT%H%M%SZ).sql"
docker compose exec -T db sh -lc 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$BACKUP_FILE"
ls -lh "$BACKUP_FILE"
```

Notes:
- The credentials used here come from the `db` container environment (`POSTGRES_USER`, `POSTGRES_DB`).
- Store backups somewhere durable (not only on the same host disk you’re trying to protect).

### Restore (from a logical dump)

#### Restore into an existing database (non-destructive)

If you want to load a dump into the current DB (may fail if objects already exist):

```bash
cat /tmp/viarah_backup.sql | docker compose exec -T db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

#### Restore from scratch (destructive)

This wipes the Postgres volume and restores into a fresh database:

```bash
docker compose down -v
docker compose up -d db

cat /tmp/viarah_backup.sql | docker compose exec -T db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

docker compose up -d
```

Follow the smoke checklist below after any restore.

## Production runner (ASGI; no `runserver`)

For production deployments, use an ASGI server (`daphne`) instead of Django’s dev server. This repo
includes `docker-compose.prod.yml` as an override that switches the `web` service command.

Example:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Reverse proxy requirements (recommended):
- Serve the app over HTTPS.
- Set `PUBLIC_APP_URL` to the external SPA base URL (for invite + password reset links).
- Ensure your reverse proxy sets `X-Forwarded-Proto: https`.
- Set `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` to include your external host/origin.

Local verification note:
- `viarah.settings.prod` defaults `SESSION_COOKIE_SECURE=1`. For local testing over HTTP, set
  `DJANGO_SECURE_COOKIES=0`.

## Upgrading between git refs/tags

Recommended workflow for upgrading between versions while keeping your existing DB data:

1) Take a DB backup (see above).
2) Fetch tags and switch to the target version:

```bash
git fetch --tags origin
git checkout <target-tag-or-ref>
```

3) Rebuild and restart the stack:

```bash
docker compose up -d --build
```

4) Run Django migrations:

```bash
docker compose exec web python manage.py migrate
```

5) Run the operator smoke checklist below.

Rollback guidance:
- If you need to roll back code, you can `git checkout <previous-ref>` and run `docker compose up -d --build`.
- If DB schema/data is incompatible, restore the DB from the pre-upgrade backup you took.

## Environment variable catalog (placeholders only)

This catalog is derived from `.env.example`, `docker-compose.yml`, and Django settings.

### Django / app runtime

- `DJANGO_SETTINGS_MODULE` (default: `viarah.settings.dev`): Which Django settings module to use.
- `DJANGO_DEBUG`: `1/0` (also supports `true/false`, `yes/no`, `on/off`).
  - Default in Django settings is `0`, but `docker-compose.yml` and `.env.example` default to `1` for local dev.
- `DJANGO_SECRET_KEY` (required): Django secret key.
  - Example placeholder: `<generate-a-long-random-secret>`
  - Do not use the repo’s dev defaults for real deployments.
- `ALLOWED_HOSTS`: Comma-separated hostnames (e.g., `example.com,api.example.com`).
- `CSRF_TRUSTED_ORIGINS` (optional): Comma-separated origins allowed to make CSRF-protected requests.
- `DJANGO_SECURE_COOKIES`: `1/0` (also supports `true/false`, `yes/no`, `on/off`).
  - Used by `viarah.settings.prod` to control `SESSION_COOKIE_SECURE` + `CSRF_COOKIE_SECURE`.
  - Default in `prod` is `1` (HTTPS-only cookies).
- `PUBLIC_APP_URL` (recommended): Absolute SPA base URL used to build links in emails (invites, account recovery).
  - Example placeholder: `https://app.example.com`
  - Local dev example (Vite): `http://localhost:5173`

### Database

- `DATABASE_URL` (required): Postgres DSN used by Django.
  - Example placeholder: `postgres://<user>:<password>@db:5432/<db_name>`

### Celery / Redis

- `CELERY_BROKER_URL` (required): Redis URL used by Celery.
  - Example placeholder: `redis://redis:6379/0`
- `CELERY_HEARTBEAT_SECONDS` (optional): Heartbeat interval used by the worker logs (seconds).

### Compose: Postgres container variables (deployment-specific)

The current `docker-compose.yml` sets these directly on the `db` service. For a real deployment, plan to override these values (and do not commit secrets to git):

- `POSTGRES_DB`: Database name (example placeholder: `<db_name>`)
- `POSTGRES_USER`: Database user (example placeholder: `<db_user>`)
- `POSTGRES_PASSWORD`: Database password (example placeholder: `<db_password>`)

### Optional integrations

These integrations are feature-gated by environment variables. If unset, the related feature may be disabled (or run in a degraded mode) until configured.

#### SMTP / email (see issue #19)

- `EMAIL_HOST`: SMTP host
- `EMAIL_PORT`: SMTP port
- `EMAIL_HOST_USER` (optional): username
- `EMAIL_HOST_PASSWORD` (optional): password **secret**
- `EMAIL_USE_TLS`: `1/0` (also supports `true/false`, `yes/no`, `on/off`)
- `DEFAULT_FROM_EMAIL`: default sender address

#### Web Push / PWA (see issue #20)

- `WEBPUSH_VAPID_PUBLIC_KEY`: VAPID public key (Base64URL; shared with clients)
- `WEBPUSH_VAPID_PRIVATE_KEY`: VAPID private key (Base64URL; secret; never commit)
- `WEBPUSH_VAPID_SUBJECT`: operator contact (e.g., `mailto:ops@example.com` or a URL)

Notes:
- Service workers + push require a secure context (HTTPS). Browsers treat `http://localhost` as a secure context exception for local dev.
- Rotating VAPID keys invalidates existing subscriptions; users must re-subscribe.
- Full details: `docs/web-push.md`.

#### GitLab live links (see issue #12)

- `VIA_RAH_ENCRYPTION_KEY` (required to store org GitLab tokens): Fernet key used to encrypt tokens at rest.
  - Set out-of-band (deployment secret store); do not commit real values.
  - If missing, ViaRah will refuse requests that attempt to store/update GitLab tokens.
- `GITLAB_METADATA_TTL_SECONDS` (optional): refresh TTL for cached GitLab link metadata (seconds, default 3600).

Notes:
- GitLab base URL + access token + optional webhook secret are configured per-organization via the API (not via env vars).

## Operator smoke checklist

Use this checklist after deploy/upgrade/restore:

- [ ] `cp .env.example .env`
- [ ] `docker compose up -d`
- [ ] `docker compose exec web python manage.py migrate`
- [ ] `curl -fsS http://localhost:8000/healthz` returns HTTP 200
- [ ] `docker compose logs --no-color --tail=200 worker` includes `celery-worker: ready` and periodic `celery-heartbeat: alive`
- [ ] Backup DB to host file:
  - `docker compose exec -T db pg_dump -U viarah -d viarah > /tmp/viarah_backup.sql` (file exists and is non-empty)
- [ ] (Optional, destructive) Restore workflow in a local environment:
  - `docker compose down -v` then `docker compose up -d db` then `cat /tmp/viarah_backup.sql | docker compose exec -T db psql -U viarah -d viarah`
- [ ] `docker compose up -d` (bring the full stack back up after restore) and re-run the `/healthz` check
