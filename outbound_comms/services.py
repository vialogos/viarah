from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

from audit.services import write_audit_event
from collaboration.models import Comment
from collaboration.services import render_markdown_to_safe_html
from core.liquid import liquid_environment
from identity.models import OrgMembership
from notifications.models import EmailDeliveryLog, EmailDeliveryStatus, NotificationEventType
from notifications.services import _enqueue_delivery_log, emit_project_event
from realtime.services import publish_org_event
from templates.models import Template, TemplateType
from work_items.models import Epic, Project, Task

from .models import OutboundDraft, OutboundDraftStatus, OutboundDraftType, OutboundWorkItemType

logger = logging.getLogger(__name__)

_LIQUID_ENV = liquid_environment()

MAX_DRAFT_BODY_CHARS = 100_000


class OutboundDraftError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _work_item_payload(*, project: Project, work_item_type: str, work_item_id: str) -> dict:
    if work_item_type == OutboundWorkItemType.TASK:
        task = (
            Task.objects.select_related("epic__project")
            .filter(id=work_item_id, epic__project=project)
            .first()
        )
        if task is None:
            raise OutboundDraftError("invalid work_item_id")
        return {
            "type": "task",
            "id": str(task.id),
            "title": task.title,
            "description": task.description,
            "status": task.status,
        }

    if work_item_type == OutboundWorkItemType.EPIC:
        epic = (
            Epic.objects.select_related("project").filter(id=work_item_id, project=project).first()
        )
        if epic is None:
            raise OutboundDraftError("invalid work_item_id")
        return {
            "type": "epic",
            "id": str(epic.id),
            "title": epic.title,
            "description": epic.description,
            "status": epic.status,
        }

    raise OutboundDraftError("invalid work_item_type")


def _render_body(*, template_body: str, context: dict) -> str:
    try:
        liquid_template = _LIQUID_ENV.from_string(template_body or "")
        rendered = str(liquid_template.render(**context) or "").strip()
    except Exception as exc:  # noqa: BLE001
        raise OutboundDraftError("failed to render Liquid template") from exc

    if not rendered:
        raise OutboundDraftError("rendered body is empty")
    if len(rendered) > MAX_DRAFT_BODY_CHARS:
        raise OutboundDraftError("rendered body is too large")
    return rendered


def create_outbound_draft(
    *,
    org,
    project: Project,
    draft_type: object,
    template_id: object,
    subject: object,
    to_user_ids: object,
    work_item_type: object,
    work_item_id: object,
    body_overrides: object,
    comment_client_safe: object,
    actor_user,
) -> OutboundDraft:
    draft_type_value = str(draft_type or "").strip()
    if draft_type_value not in set(OutboundDraftType.values):
        raise OutboundDraftError("type must be email or comment")

    try:
        template_uuid = str(template_id or "").strip()
    except Exception:
        template_uuid = ""
    if not template_uuid:
        raise OutboundDraftError("template_id is required")

    template = (
        Template.objects.filter(id=template_uuid, org=org).select_related("current_version").first()
    )
    if template is None or template.current_version_id is None:
        raise OutboundDraftError("invalid template_id")

    expected_template_type = (
        TemplateType.EMAIL if draft_type_value == OutboundDraftType.EMAIL else TemplateType.COMMENT
    )
    if template.type != expected_template_type:
        raise OutboundDraftError("template type does not match draft type")

    version = template.current_version
    if version is None:
        raise OutboundDraftError("template has no current version")

    subj = str(subject or "").strip()
    if draft_type_value == OutboundDraftType.EMAIL and not subj:
        subj = template.name

    overrides_md = None
    if body_overrides is not None:
        if isinstance(body_overrides, str):
            overrides_md = body_overrides
        elif isinstance(body_overrides, dict):
            val = body_overrides.get("body_markdown")
            if isinstance(val, str):
                overrides_md = val
        else:
            raise OutboundDraftError("body_overrides must be a string or object")

    to_ids: list[str] = []
    wi_type = None
    wi_id = None
    work_item_ctx = None

    if draft_type_value == OutboundDraftType.EMAIL:
        if not isinstance(to_user_ids, list) or not to_user_ids:
            raise OutboundDraftError("to_user_ids is required for email drafts")
        to_ids = [str(v) for v in to_user_ids if str(v).strip()]
        if not to_ids:
            raise OutboundDraftError("to_user_ids is required for email drafts")
    else:
        wi_type = str(work_item_type or "").strip()
        wi_id = str(work_item_id or "").strip()
        if not wi_type or not wi_id:
            raise OutboundDraftError(
                "work_item_type and work_item_id are required for comment drafts"
            )
        work_item_ctx = _work_item_payload(
            project=project, work_item_type=wi_type, work_item_id=wi_id
        )

    ctx: dict[str, Any] = {
        "org": {"id": str(org.id), "name": org.name},
        "project": {
            "id": str(project.id),
            "name": project.name,
            "description": project.description,
        },
        "actor": {
            "id": str(getattr(actor_user, "id", "") or ""),
            "email": str(getattr(actor_user, "email", "") or ""),
            "display_name": str(getattr(actor_user, "display_name", "") or ""),
        },
    }
    if work_item_ctx is not None:
        ctx["work_item"] = work_item_ctx

    body_md = (
        overrides_md.strip() if isinstance(overrides_md, str) and overrides_md.strip() else None
    )
    if body_md is None:
        body_md = _render_body(template_body=version.body, context=ctx)

    safe_flag = (
        bool(comment_client_safe) if draft_type_value == OutboundDraftType.COMMENT else False
    )

    draft = OutboundDraft.objects.create(
        org=org,
        project=project,
        type=draft_type_value,
        status=OutboundDraftStatus.DRAFT,
        template=template,
        template_version=version,
        subject=subj,
        body_markdown=body_md,
        to_user_ids=to_ids,
        work_item_type=wi_type or None,
        work_item_id=wi_id or None,
        comment_client_safe=safe_flag,
        created_by_user=actor_user,
    )

    write_audit_event(
        org=org,
        actor_user=actor_user,
        event_type="outbound_draft.created",
        metadata={
            "draft_id": str(draft.id),
            "project_id": str(project.id),
            "type": draft.type,
            "template_id": str(template.id),
            "template_version_id": str(version.id),
        },
    )

    return draft


def send_outbound_draft(*, draft: OutboundDraft, actor_user) -> OutboundDraft:
    if draft.status == OutboundDraftStatus.SENT:
        return draft

    now = timezone.now()

    if draft.type == OutboundDraftType.EMAIL:
        # Validate recipients exist and are org members.
        recipient_ids = [str(v) for v in (draft.to_user_ids or []) if str(v).strip()]
        if not recipient_ids:
            raise OutboundDraftError("email draft has no recipients")

        memberships = list(
            OrgMembership.objects.filter(org=draft.org, user_id__in=recipient_ids).select_related(
                "user"
            )
        )
        if not memberships:
            raise OutboundDraftError("email draft recipients are not org members")

        with transaction.atomic():
            draft.status = OutboundDraftStatus.SENT
            draft.sent_at = now
            draft.sent_by_user = actor_user
            draft.save(update_fields=["status", "sent_at", "sent_by_user", "updated_at"])

            write_audit_event(
                org=draft.org,
                actor_user=actor_user,
                event_type="outbound_draft.sent",
                metadata={"draft_id": str(draft.id), "type": draft.type},
            )

            for membership in memberships:
                to_email = str(getattr(membership.user, "email", "") or "").strip()
                if not to_email:
                    continue
                log = EmailDeliveryLog.objects.create(
                    org=draft.org,
                    project=draft.project,
                    notification_event=None,
                    outbound_draft=draft,
                    recipient_user_id=membership.user_id,
                    to_email=to_email,
                    subject=str(draft.subject or "").strip(),
                    status=EmailDeliveryStatus.QUEUED,
                    attempt_number=0,
                    error_code="",
                    error_detail="",
                    queued_at=now,
                    sent_at=None,
                )
                _enqueue_delivery_log(str(log.id))

        return draft

    if draft.type == OutboundDraftType.COMMENT:
        if not draft.work_item_type or not draft.work_item_id:
            raise OutboundDraftError("comment draft missing work item target")

        body_markdown = str(draft.body_markdown or "").rstrip()
        if not body_markdown.strip():
            raise OutboundDraftError("comment draft body is empty")

        with transaction.atomic():
            comment = None
            if draft.work_item_type == OutboundWorkItemType.TASK:
                task = (
                    Task.objects.select_related("epic__project")
                    .filter(id=draft.work_item_id, epic__project=draft.project)
                    .first()
                )
                if task is None:
                    raise OutboundDraftError("invalid work item target")
                comment = Comment.objects.create(
                    org=draft.org,
                    author_user=actor_user,
                    task=task,
                    epic=None,
                    body_markdown=body_markdown,
                    body_html=render_markdown_to_safe_html(body_markdown),
                    client_safe=bool(draft.comment_client_safe),
                )
                publish_org_event(
                    org_id=draft.org_id,
                    event_type="comment.created",
                    data={
                        "work_item_type": "task",
                        "work_item_id": str(task.id),
                        "comment_id": str(comment.id),
                    },
                )
                write_audit_event(
                    org=draft.org,
                    actor_user=actor_user,
                    event_type="comment.created",
                    metadata={"comment_id": str(comment.id), "task_id": str(task.id)},
                )
                emit_project_event(
                    org=draft.org,
                    project=draft.project,
                    event_type=NotificationEventType.COMMENT_CREATED,
                    actor_user=actor_user,
                    data={
                        "work_item_type": "task",
                        "work_item_id": str(task.id),
                        "comment_id": str(comment.id),
                    },
                    client_visible=bool(task.client_safe and draft.comment_client_safe),
                )
            else:
                epic = (
                    Epic.objects.select_related("project")
                    .filter(id=draft.work_item_id, project=draft.project)
                    .first()
                )
                if epic is None:
                    raise OutboundDraftError("invalid work item target")
                comment = Comment.objects.create(
                    org=draft.org,
                    author_user=actor_user,
                    task=None,
                    epic=epic,
                    body_markdown=body_markdown,
                    body_html=render_markdown_to_safe_html(body_markdown),
                    client_safe=False,
                )
                publish_org_event(
                    org_id=draft.org_id,
                    event_type="comment.created",
                    data={
                        "work_item_type": "epic",
                        "work_item_id": str(epic.id),
                        "comment_id": str(comment.id),
                    },
                )
                write_audit_event(
                    org=draft.org,
                    actor_user=actor_user,
                    event_type="comment.created",
                    metadata={"comment_id": str(comment.id), "epic_id": str(epic.id)},
                )
                emit_project_event(
                    org=draft.org,
                    project=draft.project,
                    event_type=NotificationEventType.COMMENT_CREATED,
                    actor_user=actor_user,
                    data={
                        "work_item_type": "epic",
                        "work_item_id": str(epic.id),
                        "comment_id": str(comment.id),
                    },
                    client_visible=False,
                )

            draft.status = OutboundDraftStatus.SENT
            draft.sent_at = now
            draft.sent_by_user = actor_user
            draft.sent_comment_id = comment.id if comment is not None else None
            draft.save(
                update_fields=[
                    "status",
                    "sent_at",
                    "sent_by_user",
                    "sent_comment_id",
                    "updated_at",
                ]
            )

            write_audit_event(
                org=draft.org,
                actor_user=actor_user,
                event_type="outbound_draft.sent",
                metadata={"draft_id": str(draft.id), "type": draft.type},
            )

        return draft

    raise OutboundDraftError("unsupported draft type")
