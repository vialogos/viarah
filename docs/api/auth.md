# API authentication (v1)

ViaRah supports API-key authentication for automation.

## Token format

- Header: `Authorization: Bearer <token>`
- Token format: `vrak_<prefix>.<secret>`
- The secret is **shown only once** at create/rotate time and is never retrievable later.

## Minting keys (PM/admin)

The API key management endpoints require a session-authenticated user with an org role of `admin` or `pm`.

Endpoints:
- `POST /api/api-keys` (create; returns secret once)
- `GET /api/api-keys?org_id=<uuid>` (list; metadata only)
- `POST /api/api-keys/<id>/revoke`
- `POST /api/api-keys/<id>/rotate` (returns secret once; invalidates old token immediately)

## Verifying a key

`GET /api/me` returns the API-key principal when a valid bearer token is provided:

```bash
curl -fsS -H "Authorization: Bearer <TOKEN>" http://localhost:8000/api/me
```

