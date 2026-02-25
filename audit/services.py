from __future__ import annotations

from typing import Any

from .models import AuditEvent


def _audit_metadata_ws_subset(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return a conservative, IDs-only-ish subset of audit metadata for websocket events.

    Realtime events are intentionally lightweight and should not carry full, arbitrary metadata.
    """

    out: dict[str, Any] = {}
    for raw_key, raw_value in (metadata or {}).items():
        key = str(raw_key or "").strip()
        if not key:
            continue

        allow_key = key.endswith("_id") or key in {
            "work_item_type",
            "work_item_id",
            "fields_changed",
        }
        if not allow_key:
            continue

        if raw_value is None or isinstance(raw_value, (str, int, float, bool)):
            out[key] = raw_value
            continue

        if isinstance(raw_value, list) and all(isinstance(v, str) for v in raw_value):
            out[key] = raw_value[:50]
            continue

    return out


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
    event = AuditEvent.objects.create(
        org=org, actor_user=actor_user, event_type=event_type, metadata=payload
    )

    try:
        from realtime.services import publish_org_event

        publish_org_event(
            org_id=org.id,
            event_type="audit_event.created",
            data={
                "audit_event_id": str(event.id),
                "event_type": event_type,
                "metadata": _audit_metadata_ws_subset(payload),
            },
        )
    except Exception:
        # Audit logging must never fail the primary request flow, including realtime hooks.
        pass

    return event
