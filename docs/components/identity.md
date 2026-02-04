# identity

Identity owns users and org membership, and provides the session-auth entrypoints used by the SPA.

## Key entrypoints

- `identity/models.py` — `User`, `Org`, `OrgMembership`, `OrgInvite`
- `identity/views.py` — request handlers
- `identity/urls.py` — route map (mounted under `/api/`)
- `viarah/settings/base.py` — `AUTH_USER_MODEL = "identity.User"`

## Models

- `User` (custom auth user; email login)
- `Org`
- `OrgMembership` (includes `role`)
- `OrgInvite` (token-hash invites)

## API routes

Mounted under `/api/` via `viarah/urls.py`:

- `/api/auth/login` → `identity.views.login_view`
- `/api/auth/logout` → `identity.views.logout_view`
- `/api/me` → `identity.views.me_view`
- `/api/invites/accept` → `identity.views.accept_invite_view`
- `/api/orgs/<org_id>/invites` → `identity.views.create_org_invite_view`
- `/api/orgs/<org_id>/memberships/<membership_id>` → `identity.views.update_membership_view`

The canonical request/response shapes live in `docs/api/openapi.yaml` and auth semantics are
documented in `docs/api/scope-map.yaml`.

## Auth notes

- Session auth uses Django’s auth system (`authenticate`, `login`, `logout`).
- `/api/me` is decorated with `ensure_csrf_cookie` so browser clients can establish a CSRF cookie.
- API key principals are also supported for `/api/me` when `request.api_key_principal` is set (see
  `api_keys/middleware.py`).

## Interactions / dependencies

- Writes audit events for org invites/membership role changes via `audit.services.write_audit_event`.
- Most other apps reference `identity.Org` and/or `identity.User` for ownership and access control.
