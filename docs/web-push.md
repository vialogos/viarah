# Web Push / PWA (v1)

This document covers ViaRah’s Web Push + PWA bootstrap (Issue #20) and the SPA-based subscription
controls (Issue #32).

## Requirements / constraints

- **Secure context**: service workers + push subscriptions require HTTPS in production. Browsers treat `http://localhost` as a secure context exception for local development.
- **No secrets in git**: the VAPID private key must come from a secret store / environment variables only.

## Environment variables

- `WEBPUSH_VAPID_PUBLIC_KEY` (Base64URL, no padding)
- `WEBPUSH_VAPID_PRIVATE_KEY` (Base64URL, no padding) **secret**
- `WEBPUSH_VAPID_SUBJECT` (operator contact), e.g. `mailto:ops@example.com`

If any are missing, ViaRah treats push as disabled (API will return 503 for VAPID public key).

## Generating a VAPID keypair

From the repo root (with dependencies installed):

```bash
python3 manage.py shell -c 'from py_vapid import Vapid; from py_vapid.utils import b64urlencode, num_to_bytes; from cryptography.hazmat.primitives import serialization; v=Vapid(); v.generate_keys(); pub=b64urlencode(v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)); priv=b64urlencode(num_to_bytes(v.private_key.private_numbers().private_value, 32)); print(\"WEBPUSH_VAPID_PUBLIC_KEY=\", pub); print(\"WEBPUSH_VAPID_PRIVATE_KEY=\", priv);'
```

Set the values via your secret store / deployment environment, and set `WEBPUSH_VAPID_SUBJECT`.

## Rotation

Rotating the VAPID keypair invalidates existing browser subscriptions. Users must re-subscribe after rotation.

## API endpoints (session auth only)

- `GET /api/push/vapid_public_key` → `{ public_key }`
- `GET /api/push/subscriptions` → list current user subscriptions (keys are redacted)
- `POST /api/push/subscriptions` → upsert current browser subscription
- `DELETE /api/push/subscriptions/<subscription_id>` → delete a subscription row

## SPA flow (primary UX)

The Vue SPA provides “Push (this device)” controls inside **Notification Preferences** to manage
the push subscription for the *current browser/device*.

High-level flow:
- Subscribe:
  - Requests notification permission.
  - Registers the SPA service worker at `/service-worker.js` (served by the SPA origin; see
    `frontend/public/service-worker.js`).
  - Fetches the VAPID public key from `GET /api/push/vapid_public_key` (returns 503 when push is not
    configured).
  - Creates a browser push subscription and POSTs it to `POST /api/push/subscriptions`.
- Unsubscribe:
  - Finds the current browser subscription and deletes the matching server row (matched by
    `endpoint`) via `DELETE /api/push/subscriptions/<id>`.
  - Unsubscribes locally in the browser.

Notes:
- Notification preferences are still project-scoped: users must enable `push` for the relevant
  event type (e.g., `assignment.changed`) for push delivery to occur.
- Subscriptions are per browser/device. Users can have multiple active subscriptions.

## Manual smoke page (fallback/test page)

The backend root (`GET /`) serves a minimal page that registers the service worker and provides “Enable/Disable notifications” controls for the Issue #20 smoke plan.
