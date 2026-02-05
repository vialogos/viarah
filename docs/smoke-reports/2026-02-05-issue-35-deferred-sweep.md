# Deferred smoke sweep — Issue #35 (2026-02-05)

Consolidated local Docker Compose + browser smoke steps deferred from:
- #20 (Web Push / PWA v1)
- #24 (API completeness + automation smoke)
- #28 (Bootstrap v1)
- #32 (Push notifications v1.1)
- #34 (GitLab live links UI v1)

## Environment

- Run date (UTC): 2026-02-05
- Repo: `vialogos-labs/viarah`
- Base commit (at start): `1bb29cc`
- Docker: `Docker version 28.2.2`
- Docker Compose: `v2.36.2`
- Node: `v22.16.0`
- npm: `11.8.0`
- Local URLs:
  - Backend: `http://localhost:8000`
  - SPA (Vite): `http://localhost:5173`

## Local-only configuration (values redacted)

Set via `.env` (do not commit):
- `WEBPUSH_VAPID_PUBLIC_KEY`
- `WEBPUSH_VAPID_PRIVATE_KEY` (secret)
- `WEBPUSH_VAPID_SUBJECT`
- `VIA_RAH_ENCRYPTION_KEY` (secret; required for GitLab token storage)

## Notable fix required to run the sweep

`docker-compose.yml` now passes the push + encryption env vars into `web` and `worker`.

Without this, `GET /api/push/vapid_public_key` returned `503 {"error": "push is not configured"}` even when `.env` was populated.

## Checklist results

### 0) Baseline (Compose + frontend) — PASS

- `cp .env.example .env`
- `docker compose down -v`
- `docker compose up -d`
- `docker compose exec web python manage.py migrate` (OK)
- `curl -fsS http://localhost:8000/healthz` → `200`
- `docker compose exec web python manage.py test` (OK)
- `cd frontend && npm install` (OK)
- `cd frontend && npm run dev -- --host 0.0.0.0 --port 5173` (OK; `curl -fsS http://localhost:5173/` → `200`)

### 1) API completeness (#24) — PASS

- `docker compose exec web python scripts/api_completeness_check.py` (OK)
  - Note: required `docker compose exec web python -m pip install -r requirements-dev.txt` inside the container to provide PyYAML.

### 2) Bootstrap v1 (#28) — PASS (non-UI)

- `docker compose exec web python manage.py bootstrap_v1 ...` (created org/PM/project/key)
- Re-run with same args → idempotent reuse (OK)
- UI login verification: **PENDING** (manual; see below)

### 3) Web Push / PWA (#20) — PARTIAL

- `curl -fsS http://localhost:8000/manifest.webmanifest | head -c 200` (OK; includes `start_url`)
- Session-auth gate (programmatic): `GET /api/push/vapid_public_key` returns `200` when logged in (OK)
- Service worker + subscribe/unsubscribe + push delivery: **PENDING** (manual)

### 4) Push notifications v1.1 (#32) — PARTIAL

- `docker compose exec web python manage.py test notifications push` (OK)
- `cd frontend && npm run lint && npm run typecheck` (OK)
- UI subscribe + preferences + assignment.changed push delivery: **PENDING** (manual)

### 5) GitLab live links UI (#34) — PARTIAL

- `docker compose exec web python manage.py test integrations` (OK)
- `cd frontend && npm run build` (OK)
- UI settings + PAT write-only field + validate + add/list/delete links: **PENDING** (manual; requires PAT)

## Manual browser checklist (Chrome/Edge)

- [ ] Sign in via SPA (`http://localhost:5173/login`) as the bootstrap PM and confirm the created project is visible/selected.
- [ ] In Chrome/Edge, open `http://localhost:8000/` and confirm the service worker registers (DevTools → Application → Service Workers).
- [ ] Click “Enable notifications” (subscribe), grant permission, then verify a subscription row exists in the DB (Django admin or shell).
- [ ] Trigger a test push (`python manage.py push_test --email <pm-email>`) and confirm the browser receives a notification.
- [ ] Click “Disable notifications” (unsubscribe) and verify the subscription row is deleted.
- [ ] Trigger the test push again and confirm no push is received.
- [ ] Assignment.changed push flows (User A/B, preferences on/off, self-assign negative).
- [ ] GitLab live links UI flows:
  - Settings page loads/saves `base_url`
  - PAT is write-only (blank after save + refresh) and not leaked in error messages
  - “Validate” shows status
  - Work detail GitLab links section renders; add/list/delete links; missing token case renders metadata-unavailable + CTA

## Evidence / artifacts

Per issue #35: capture and attach `docker compose ps`, `docker compose logs ...`, and relevant `vl-ui-snapshot` artifacts **only if** any checkbox fails.

