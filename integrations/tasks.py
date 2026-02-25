from __future__ import annotations

import datetime
from typing import Any

from celery import shared_task
from django.utils import timezone

from .gitlab import GitLabClient, GitLabHttpError
from .models import GitLabWebhookDelivery, TaskGitLabLink
from .selectors import get_effective_gitlab_integration_for_org
from .services import IntegrationConfigError, decrypt_token
from realtime.services import publish_org_event


def _retry_after_seconds(headers: dict[str, str]) -> int | None:
    raw = str(headers.get("Retry-After", "")).strip()
    if not raw:
        return None
    try:
        return max(int(raw), 1)
    except ValueError:
        return None


def _assignees_payload(assignees: Any) -> list[dict[str, str]]:
    if not isinstance(assignees, list):
        return []
    cleaned: list[dict[str, str]] = []
    for row in assignees:
        if not isinstance(row, dict):
            continue
        username = str(row.get("username", "")).strip()
        name = str(row.get("name", "")).strip()
        if not username and not name:
            continue
        cleaned.append({"username": username, "name": name})
    return cleaned


def _labels_payload(labels: Any) -> list[str]:
    if not isinstance(labels, list):
        return []
    return [str(v) for v in labels if str(v).strip()]


def _participants_payload(participants: Any) -> list[dict[str, str | int]]:
    if not isinstance(participants, list):
        return []
    cleaned: list[dict[str, str | int]] = []
    seen: set[str] = set()
    for row in participants:
        if not isinstance(row, dict):
            continue

        gitlab_id: int | None
        raw_id = row.get("id")
        try:
            gitlab_id = int(raw_id)
        except (TypeError, ValueError):
            gitlab_id = None

        username = str(row.get("username", "")).strip()
        name = str(row.get("name", "")).strip()
        if not username and not name and gitlab_id is None:
            continue

        key = username or str(gitlab_id or "") or name
        if not key or key in seen:
            continue
        seen.add(key)

        payload: dict[str, str | int] = {}
        if gitlab_id is not None:
            payload["id"] = gitlab_id
        if username:
            payload["username"] = username
        if name:
            payload["name"] = name
        cleaned.append(payload)
    return cleaned


@shared_task
def refresh_gitlab_link_metadata(link_id: str) -> None:
    """Refresh cached GitLab metadata for a `TaskGitLabLink`.

    Trigger: Enqueued on link create, stale reads, and webhook processing.
    Inputs: `link_id` is the `TaskGitLabLink` UUID (string form).
    Idempotency: Safe to re-run; updates cached fields and sync timestamps, and records errors.
    Side effects: Calls GitLab over HTTP and updates the link row (rate limits, etc.).
    """
    now = timezone.now()
    link = TaskGitLabLink.objects.select_related("task__epic__project").filter(id=link_id).first()
    if link is None:
        return

    org_id = link.task.epic.project.org_id

    def _publish(*, reason: str, error_code: str | None = None) -> None:
        publish_org_event(
            org_id=org_id,
            event_type="gitlab_link.updated",
            data={
                "project_id": str(link.task.epic.project_id),
                "task_id": str(link.task_id),
                "link_id": str(link.id),
                "gitlab_type": str(link.gitlab_type),
                "gitlab_iid": int(link.gitlab_iid),
                "reason": reason,
                "error_code": error_code,
            },
        )

    link.last_sync_attempt_at = now
    link.save(update_fields=["last_sync_attempt_at", "updated_at"])

    integration, _integration_source = get_effective_gitlab_integration_for_org(org_id=org_id)
    if integration is None:
        TaskGitLabLink.objects.filter(id=link.id).update(
            last_sync_error_code="missing_integration",
            last_sync_error_at=now,
            updated_at=now,
        )
        _publish(reason="sync_error", error_code="missing_integration")
        return

    if not integration.token_ciphertext:
        TaskGitLabLink.objects.filter(id=link.id).update(
            last_sync_error_code="missing_token",
            last_sync_error_at=now,
            updated_at=now,
        )
        _publish(reason="sync_error", error_code="missing_token")
        return

    try:
        token = decrypt_token(integration.token_ciphertext)
    except IntegrationConfigError as exc:
        message = str(exc)
        code = "encryption_key_missing"
        if "ciphertext" in message:
            code = "invalid_token_ciphertext"
        elif "invalid" in message:
            code = "encryption_key_invalid"
        TaskGitLabLink.objects.filter(id=link.id).update(
            last_sync_error_code=code,
            last_sync_error_at=now,
            updated_at=now,
        )
        _publish(reason="sync_error", error_code=code)
        return

    client = GitLabClient(base_url=integration.base_url, token=token)

    try:
        if link.gitlab_type == TaskGitLabLink.GitLabType.ISSUE:
            payload = client.get_issue(project_path=link.project_path, issue_iid=link.gitlab_iid)
        else:
            payload = client.get_merge_request(
                project_path=link.project_path, merge_request_iid=link.gitlab_iid
            )
    except GitLabHttpError as exc:
        if exc.status_code == 429:
            retry_seconds = _retry_after_seconds(exc.headers) or 60
            rate_limited_until = now + datetime.timedelta(seconds=retry_seconds)
            TaskGitLabLink.objects.filter(id=link.id).update(
                last_sync_error_code="rate_limited",
                last_sync_error_at=now,
                rate_limited_until=rate_limited_until,
                updated_at=now,
            )
            _publish(reason="sync_error", error_code="rate_limited")
            return

        if exc.status_code in {401, 403}:
            error_code = "auth_error"
        elif exc.status_code == 404:
            error_code = "not_found"
        elif exc.status_code == 0:
            error_code = "network_error"
        else:
            error_code = f"http_{exc.status_code}"

        TaskGitLabLink.objects.filter(id=link.id).update(
            last_sync_error_code=error_code,
            last_sync_error_at=now,
            updated_at=now,
        )
        _publish(reason="sync_error", error_code=error_code)
        return

    title = str(payload.get("title", "")).strip()
    state = str(payload.get("state", "")).strip()
    labels = _labels_payload(payload.get("labels"))
    assignees = _assignees_payload(payload.get("assignees"))
    participants = _participants_payload(payload.get("participants"))

    TaskGitLabLink.objects.filter(id=link.id).update(
        cached_title=title,
        cached_state=state,
        cached_labels=labels,
        cached_assignees=assignees,
        cached_participants=participants,
        last_synced_at=now,
        last_sync_error_code="",
        last_sync_error_at=None,
        rate_limited_until=None,
        updated_at=now,
    )
    _publish(reason="synced", error_code=None)


@shared_task
def process_gitlab_webhook_delivery(delivery_id: str) -> None:
    """Process a stored GitLab webhook delivery by refreshing matching task links.

    Trigger: Enqueued by `integrations.views.gitlab_webhook_view` after persisting the delivery.
    Inputs: `delivery_id` is the `GitLabWebhookDelivery` UUID (string form).
    Idempotency: Safe to retry; marks the delivery processed/failed and enqueues link refresh tasks.
    Side effects: Enqueues `refresh_gitlab_link_metadata` tasks and updates the delivery status.
    """
    now = timezone.now()
    delivery = GitLabWebhookDelivery.objects.filter(id=delivery_id).first()
    if delivery is None:
        return

    project_path = str(delivery.project_path or "").strip()
    gitlab_type = str(delivery.gitlab_type or "").strip()
    gitlab_iid = delivery.gitlab_iid

    if not project_path or not gitlab_type or not gitlab_iid:
        GitLabWebhookDelivery.objects.filter(id=delivery.id).update(
            status=GitLabWebhookDelivery.Status.FAILED,
            processed_at=now,
            last_error="unsupported payload",
        )
        return

    links = TaskGitLabLink.objects.filter(
        project_path=project_path,
        gitlab_type=gitlab_type,
        gitlab_iid=gitlab_iid,
        task__epic__project__org_id=delivery.org_id,
    ).values_list("id", flat=True)

    for link_id in list(links):
        refresh_gitlab_link_metadata.delay(str(link_id))

    GitLabWebhookDelivery.objects.filter(id=delivery.id).update(
        status=GitLabWebhookDelivery.Status.PROCESSED,
        processed_at=now,
        last_error="",
    )
