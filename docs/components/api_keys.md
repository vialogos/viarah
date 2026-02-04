# api_keys

API keys provide bearer-token authentication for `/api/...` endpoints that support service access.

## Key entrypoints

- `api_keys/models.py` — `ApiKey` (+ `Scope` values)
- `api_keys/services.py` — token format + mint/rotate/revoke/verify helpers
- `api_keys/middleware.py` — parses `Authorization: Bearer ...` and sets `request.api_key_principal`
  (and bypasses CSRF for bearer requests)
- `api_keys/views.py`, `api_keys/urls.py` — CRUD endpoints for API keys
- `docs/api/auth.md` — consumer-facing token semantics

## Models

- `ApiKey` (org-scoped; optional `project_id` restriction; `scopes` list)

## Token format

`api_keys.services.parse_token()` enforces a ViaRah-specific token prefix:

- `vrak_<prefix>.<secret>`

Only the hashed secret is stored server-side (`ApiKey.secret_hash`).

## API routes

Mounted under `/api/`:

- `/api/api-keys` → `api_keys.views.api_keys_collection_view`
- `/api/api-keys/<api_key_id>/revoke` → `api_keys.views.revoke_api_key_view`
- `/api/api-keys/<api_key_id>/rotate` → `api_keys.views.rotate_api_key_view`

The canonical request/response shapes live in `docs/api/openapi.yaml` and auth semantics are in
`docs/api/scope-map.yaml`.

## Scopes

`ApiKey.Scope` values are currently `read` and `write`.

Most API handlers treat `read` as a subset of `write` (see `_principal_has_scope()` helpers across
`<app>/views.py`).

## Interactions / dependencies

- Many apps check `request.api_key_principal` for authZ decisions (org match, optional project
  restriction via `ApiKey.project_id`, scope checks).
- Writes audit events on create/rotate/revoke via `audit.services.write_audit_event`.
