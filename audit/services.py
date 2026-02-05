from __future__ import annotations

from typing import Any

from .models import AuditEvent


def assert_metadata_is_safe(metadata: dict[str, Any]) -> None:
    """Validate audit metadata does not contain obvious sensitive keys.

    This is a defense-in-depth guardrail to avoid persisting secrets in audit logs.
    It only inspects metadata keys (not values) and raises `ValueError` on a likely-sensitive key.
    """
    sensitive_substrings = {"token", "password", "secret", "api_key", "apikey"}
    for key in metadata.keys():
        lowered = str(key).lower()
        if any(s in lowered for s in sensitive_substrings):
            raise ValueError(f"Audit metadata contains sensitive key: {key!r}")


def write_audit_event(
    *, org, actor_user, event_type: str, metadata: dict[str, Any] | None = None
) -> AuditEvent:
    """Create an `AuditEvent` row after enforcing metadata safety.

    Callers should record non-sensitive, high-level context (ids, event types, and safe flags) and
    avoid storing any raw secrets, tokens, or PII beyond what is already persisted elsewhere.
    """
    payload = metadata or {}
    assert_metadata_is_safe(payload)
    return AuditEvent.objects.create(
        org=org, actor_user=actor_user, event_type=event_type, metadata=payload
    )
