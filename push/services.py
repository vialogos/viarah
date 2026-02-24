from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from pywebpush import webpush

from integrations.services import IntegrationConfigError, decrypt_token, encrypt_token

from .models import PushSubscription, PushVapidConfig


def push_is_configured() -> bool:
    """Return True when the required VAPID settings are configured for Web Push delivery."""
    cfg = _effective_vapid()
    return bool(cfg and cfg.get("public_key") and cfg.get("private_key") and cfg.get("subject"))


def vapid_public_key() -> str | None:
    """Return the configured VAPID public key (or None when missing)."""
    cfg = _effective_vapid()
    value = str(cfg.get("public_key", "") if cfg else "").strip()
    return value or None


def vapid_config_status() -> dict[str, Any]:
    """Return a safe VAPID config status payload for admin UIs (never includes the private key)."""
    cfg = _effective_vapid()
    return {
        "configured": bool(cfg and cfg.get("public_key") and cfg.get("private_key") and cfg.get("subject")),
        "source": str(cfg.get("source") if cfg else "missing"),
        "public_key": str(cfg.get("public_key") if cfg else "") or None,
        "subject": str(cfg.get("subject") if cfg else "") or None,
        "private_key_configured": bool(cfg and cfg.get("private_key")),
        "encryption_configured": bool(cfg and cfg.get("encryption_configured")),
        "error_code": str(cfg.get("error_code") if cfg else "missing"),
    }


def set_vapid_config(*, public_key: str, private_key: str, subject: str) -> None:
    """Set the active VAPID configuration in the database (encrypted private key)."""
    pub = str(public_key or "").strip()
    priv = str(private_key or "").strip()
    sub = str(subject or "").strip()
    row, _ = PushVapidConfig.objects.get_or_create(key="default")

    priv_ciphertext: str | None = None
    if priv:
        priv_ciphertext = encrypt_token(priv)

    row.vapid_public_key = pub
    row.vapid_private_key_ciphertext = priv_ciphertext
    row.vapid_subject = sub
    row.save(update_fields=["vapid_public_key", "vapid_private_key_ciphertext", "vapid_subject", "updated_at"])


def clear_vapid_config() -> None:
    PushVapidConfig.objects.filter(key="default").delete()


def generate_and_set_vapid_config(*, subject: str) -> dict[str, str]:
    """Generate a new VAPID keypair and store it in the DB (encrypted). Returns the public key."""
    from base64 import urlsafe_b64encode

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    def b64url(data: bytes) -> str:
        return urlsafe_b64encode(data).decode("utf-8").rstrip("=")

    def num_to_bytes(value: int, length: int) -> bytes:
        return int(value).to_bytes(length, byteorder="big")

    private_key = ec.generate_private_key(ec.SECP256R1())
    pub_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    priv_num = private_key.private_numbers().private_value
    priv_bytes = num_to_bytes(priv_num, 32)

    public_key = b64url(pub_bytes)
    private_key_b64 = b64url(priv_bytes)
    set_vapid_config(public_key=public_key, private_key=private_key_b64, subject=subject)
    return {"public_key": public_key}


def _effective_vapid() -> dict[str, Any] | None:
    """Return effective VAPID config with plaintext private key (internal-only)."""
    row = PushVapidConfig.objects.filter(key="default").first()
    if row is not None:
        pub = str(row.vapid_public_key or "").strip()
        sub = str(row.vapid_subject or "").strip()
        ciphertext = row.vapid_private_key_ciphertext

        if not pub or not sub or not ciphertext:
            return {
                "source": "db",
                "public_key": pub,
                "private_key": "",
                "subject": sub,
                "encryption_configured": True,
                "error_code": "missing_config",
            }

        try:
            priv = decrypt_token(ciphertext)
        except IntegrationConfigError as exc:
            message = str(exc)
            code = "encryption_key_missing"
            if "invalid" in message:
                code = "encryption_key_invalid"
            if "ciphertext" in message:
                code = "invalid_token_ciphertext"
            return {
                "source": "db",
                "public_key": pub,
                "private_key": "",
                "subject": sub,
                "encryption_configured": False,
                "error_code": code,
            }

        return {
            "source": "db",
            "public_key": pub,
            "private_key": priv,
            "subject": sub,
            "encryption_configured": True,
            "error_code": None,
        }

    pub_env = str(getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", "") or "").strip()
    priv_env = str(getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", "") or "").strip()
    sub_env = str(getattr(settings, "WEBPUSH_VAPID_SUBJECT", "") or "").strip()
    if not pub_env and not priv_env and not sub_env:
        return None

    return {
        "source": "env",
        "public_key": pub_env,
        "private_key": priv_env,
        "subject": sub_env,
        "encryption_configured": True,
        "error_code": None,
    }


def send_push_to_subscription(*, subscription: PushSubscription, payload: dict[str, Any]) -> None:
    """Send a single Web Push message to one subscription.

    This is a best-effort operation: when push is not configured, it returns without raising.
    """
    cfg = _effective_vapid()
    if not cfg or not cfg.get("public_key") or not cfg.get("private_key") or not cfg.get("subject"):
        return

    private_key = str(cfg.get("private_key") or "").strip()
    subject = str(cfg.get("subject") or "").strip()
    if not private_key or not subject:
        return

    webpush(
        subscription_info={
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
        },
        data=json.dumps(payload or {}),
        vapid_private_key=private_key,
        vapid_claims={"sub": subject},
        ttl=60,
    )
