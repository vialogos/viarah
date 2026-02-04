# Web Push / PWA (v1)

This document covers ViaRah’s Web Push + PWA bootstrap (Issue #20).

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
python manage.py shell -c 'from py_vapid import Vapid; from py_vapid.utils import b64urlencode, num_to_bytes; from cryptography.hazmat.primitives import serialization; v=Vapid(); v.generate_keys(); pub=b64urlencode(v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)); priv=b64urlencode(num_to_bytes(v.private_key.private_numbers().private_value, 32)); print(\"WEBPUSH_VAPID_PUBLIC_KEY=\", pub); print(\"WEBPUSH_VAPID_PRIVATE_KEY=\", priv);'
```

Set the values via your secret store / deployment environment, and set `WEBPUSH_VAPID_SUBJECT`.

## Rotation

Rotating the VAPID keypair invalidates existing browser subscriptions. Users must re-subscribe after rotation.

## API endpoints (session auth only)

- `GET /api/push/vapid_public_key` → `{ public_key }`
- `GET /api/push/subscriptions` → list current user subscriptions (keys are redacted)
- `POST /api/push/subscriptions` → upsert current browser subscription
- `DELETE /api/push/subscriptions/<subscription_id>` → delete a subscription row

## Manual smoke page

The backend root (`GET /`) serves a minimal page that registers the service worker and provides “Enable/Disable notifications” controls for the Issue #20 smoke plan.

