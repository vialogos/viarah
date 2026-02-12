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
- `OrgMembership` (includes `role` plus profile + availability fields for attribution)
- `OrgInvite` (token-hash invites)

## API routes

Mounted under `/api/` via `viarah/urls.py`:

- `/api/auth/login` → `identity.views.login_view`
- `/api/auth/logout` → `identity.views.logout_view`
- `/api/me` → `identity.views.me_view`
- `/api/invites/accept` → `identity.views.accept_invite_view`
- `/api/orgs/<org_id>/invites` → `identity.views.create_org_invite_view`
- `/api/orgs/<org_id>/memberships` → `identity.views.org_memberships_collection_view`
- `/api/orgs/<org_id>/memberships/<membership_id>` → `identity.views.update_membership_view`

The canonical request/response shapes live in `docs/api/openapi.yaml` and auth semantics are
documented in `docs/api/scope-map.yaml`.

## Auth notes

- Session auth uses Django’s auth system (`authenticate`, `login`, `logout`).
- `/api/me` is decorated with `ensure_csrf_cookie` so browser clients can establish a CSRF cookie.
- API key principals are also supported for `/api/me` when `request.api_key_principal` is set (see
  `api_keys/middleware.py`).

## API/CLI examples (session + CSRF)

These endpoints are session-authenticated and require CSRF for state-changing requests.

```bash
BASE_URL="http://localhost:8000"
COOKIE_JAR="/tmp/viarah.cookies.txt"

# 1) Mint csrftoken cookie (anonymous is fine)
curl -fsS -c "$COOKIE_JAR" "$BASE_URL/api/me" >/dev/null
CSRF="$(awk '$6 == "csrftoken" {print $7}' "$COOKIE_JAR" | tail -n1)"

# 2) Login (creates session)
curl -fsS -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
  -H "X-CSRFToken: $CSRF" -H "Content-Type: application/json" \
  -d '{"email":"pm@example.com","password":"<PASSWORD>"}' \
  "$BASE_URL/api/auth/login" >/dev/null

# Re-read CSRF in case it rotated during login.
CSRF="$(awk '$6 == "csrftoken" {print $7}' "$COOKIE_JAR" | tail -n1)"
```

Create an invite:

```bash
ORG_ID="<ORG_UUID>"

curl -fsS -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
  -H "X-CSRFToken: $CSRF" -H "Content-Type: application/json" \
  -d '{"email":"invitee@example.com","role":"member"}' \
  "$BASE_URL/api/orgs/$ORG_ID/invites"

# Response includes:
# - token (shown once)
# - invite_url (relative SPA path like /invite/accept?token=...)
```

Accept an invite (as the invitee, logged out):

```bash
INVITEE_COOKIE_JAR="/tmp/viarah.invitee.cookies.txt"

curl -fsS -c "$INVITEE_COOKIE_JAR" "$BASE_URL/api/me" >/dev/null
INVITEE_CSRF="$(awk '$6 == "csrftoken" {print $7}' "$INVITEE_COOKIE_JAR" | tail -n1)"

TOKEN="<TOKEN_FROM_INVITE_RESPONSE>"

curl -fsS -b "$INVITEE_COOKIE_JAR" -c "$INVITEE_COOKIE_JAR" \
  -H "X-CSRFToken: $INVITEE_CSRF" -H "Content-Type: application/json" \
  -d "{\"token\":\"$TOKEN\",\"password\":\"<NEW_OR_EXISTING_PASSWORD>\",\"display_name\":\"Invitee\"}" \
  "$BASE_URL/api/invites/accept" >/dev/null
```

List memberships:

```bash
curl -fsS -b "$COOKIE_JAR" "$BASE_URL/api/orgs/$ORG_ID/memberships"
```

Change a member’s role:

```bash
MEMBERSHIP_ID="<MEMBERSHIP_UUID>"

curl -fsS -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
  -H "X-CSRFToken: $CSRF" -H "Content-Type: application/json" \
  -X PATCH -d '{"role":"pm"}' \
  "$BASE_URL/api/orgs/$ORG_ID/memberships/$MEMBERSHIP_ID"
```

Update member profile fields / availability (Admin/PM):

```bash
curl -fsS -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
  -H "X-CSRFToken: $CSRF" -H "Content-Type: application/json" \
  -X PATCH \
  -d '{"display_name":"Ada","title":"Project manager","skills":["Roadmaps","QA"],"bio":"Client-facing attribution bio","availability_status":"limited","availability_hours_per_week":20,"availability_next_available_at":null,"availability_notes":"Part-time until next sprint."}' \
  "$BASE_URL/api/orgs/$ORG_ID/memberships/$MEMBERSHIP_ID"

# availability_status values: unknown, available, limited, unavailable
```

## Interactions / dependencies

- Writes audit events for org invites/membership role changes via `audit.services.write_audit_event`.
- Most other apps reference `identity.Org` and/or `identity.User` for ownership and access control.
