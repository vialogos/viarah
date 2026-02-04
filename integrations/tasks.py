from __future__ import annotations

import datetime
from typing import Any

from celery import shared_task
from django.utils import timezone

from .gitlab import GitLabClient, GitLabHttpError
from .models import GitLabWebhookDelivery, OrgGitLabIntegration, TaskGitLabLink
from .services import IntegrationConfigError, decrypt_token


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


@shared_task
def refresh_gitlab_link_metadata(link_id: str) -> None:
    now = timezone.now()
    link = TaskGitLabLink.objects.select_related("task__epic__project").filter(id=link_id).first()
    if link is None:
        return

    link.last_sync_attempt_at = now
    link.save(update_fields=["last_sync_attempt_at", "updated_at"])

    org_id = link.task.epic.project.org_id
    integration = OrgGitLabIntegration.objects.filter(org_id=org_id).first()
    if integration is None:
        TaskGitLabLink.objects.filter(id=link.id).update(
            last_sync_error_code="missing_integration",
            last_sync_error_at=now,
            updated_at=now,
        )
        return

    if not integration.token_ciphertext:
        TaskGitLabLink.objects.filter(id=link.id).update(
            last_sync_error_code="missing_token",
            last_sync_error_at=now,
            updated_at=now,
        )
        return

    try:
        token = decrypt_token(integration.token_ciphertext)
    except IntegrationConfigError as exc:
        code = "encryption_key_missing"
        if "ciphertext" in str(exc):
            code = "invalid_token_ciphertext"
        TaskGitLabLink.objects.filter(id=link.id).update(
            last_sync_error_code=code,
            last_sync_error_at=now,
            updated_at=now,
        )
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
        return

    title = str(payload.get("title", "")).strip()
    state = str(payload.get("state", "")).strip()
    labels = _labels_payload(payload.get("labels"))
    assignees = _assignees_payload(payload.get("assignees"))

    TaskGitLabLink.objects.filter(id=link.id).update(
        cached_title=title,
        cached_state=state,
        cached_labels=labels,
        cached_assignees=assignees,
        last_synced_at=now,
        last_sync_error_code="",
        last_sync_error_at=None,
        rate_limited_until=None,
        updated_at=now,
    )


@shared_task
def process_gitlab_webhook_delivery(delivery_id: str) -> None:
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
