from __future__ import annotations

import json

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from identity.models import Org, OrgMembership
from work_items.models import Project

from .models import OutboundDraft, OutboundDraftStatus
from .services import OutboundDraftError, create_outbound_draft, send_outbound_draft


def _json_error(message: str, *, status: int) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def _parse_json(request: HttpRequest) -> dict:
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise ValueError("invalid JSON") from None

    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")

    return payload


def _require_session_user(request: HttpRequest):
    if getattr(request, "api_key_principal", None) is not None:
        return None, _json_error("forbidden", status=403)
    if not request.user.is_authenticated:
        return None, _json_error("unauthorized", status=401)
    return request.user, None


def _require_org(org_id) -> Org | None:
    return Org.objects.filter(id=org_id).first()


def _require_project(org: Org, project_id) -> Project | None:
    return Project.objects.filter(id=project_id, org=org).first()


def _require_membership(user, org: Org, *, allowed_roles: set[str]) -> OrgMembership | None:
    return (
        OrgMembership.objects.filter(user=user, org=org, role__in=allowed_roles)
        .select_related("org")
        .first()
    )


def _draft_dict(draft: OutboundDraft) -> dict:
    return {
        "id": str(draft.id),
        "org_id": str(draft.org_id),
        "project_id": str(draft.project_id),
        "type": draft.type,
        "status": draft.status,
        "template_id": str(draft.template_id),
        "template_version_id": str(draft.template_version_id),
        "subject": draft.subject,
        "body_markdown": draft.body_markdown,
        "to_user_ids": list(draft.to_user_ids or []),
        "work_item_type": draft.work_item_type,
        "work_item_id": str(draft.work_item_id) if draft.work_item_id else None,
        "comment_client_safe": bool(draft.comment_client_safe),
        "sent_comment_id": str(draft.sent_comment_id) if draft.sent_comment_id else None,
        "created_at": draft.created_at.isoformat(),
        "updated_at": draft.updated_at.isoformat(),
        "sent_at": draft.sent_at.isoformat() if draft.sent_at else None,
    }


@require_http_methods(["GET", "POST"])
def outbound_drafts_collection_view(request: HttpRequest, org_id, project_id) -> JsonResponse:
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_membership(
        user, org, allowed_roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
    )
    if membership is None:
        return _json_error("forbidden", status=403)

    project = _require_project(org, project_id)
    if project is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        status = str(request.GET.get("status", "")).strip()
        if status and status not in set(OutboundDraftStatus.values):
            return _json_error("invalid status", status=400)

        qs = OutboundDraft.objects.filter(org=org, project=project).order_by("-created_at", "-id")
        if status:
            qs = qs.filter(status=status)
        drafts = list(qs[:200])
        return JsonResponse({"drafts": [_draft_dict(d) for d in drafts]})

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    try:
        draft = create_outbound_draft(
            org=org,
            project=project,
            draft_type=payload.get("type"),
            template_id=payload.get("template_id"),
            subject=payload.get("subject"),
            to_user_ids=payload.get("to_user_ids"),
            work_item_type=payload.get("work_item_type"),
            work_item_id=payload.get("work_item_id"),
            body_overrides=payload.get("body_overrides"),
            comment_client_safe=payload.get("comment_client_safe"),
            actor_user=user,
        )
    except OutboundDraftError as exc:
        return _json_error(exc.message, status=400)

    return JsonResponse({"draft": _draft_dict(draft)}, status=201)


@require_http_methods(["GET", "PATCH"])
def outbound_draft_detail_view(request: HttpRequest, org_id, draft_id) -> JsonResponse:
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_membership(
        user, org, allowed_roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
    )
    if membership is None:
        return _json_error("forbidden", status=403)

    draft = OutboundDraft.objects.filter(id=draft_id, org=org).first()
    if draft is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        return JsonResponse({"draft": _draft_dict(draft)})

    if draft.status != OutboundDraftStatus.DRAFT:
        return _json_error("draft is already sent", status=400)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    if "subject" in payload:
        draft.subject = str(payload.get("subject", "")).strip()
    if "body_markdown" in payload:
        draft.body_markdown = str(payload.get("body_markdown", "")).rstrip()
    if "to_user_ids" in payload and draft.type == "email":
        if not isinstance(payload.get("to_user_ids"), list):
            return _json_error("to_user_ids must be a list", status=400)
        draft.to_user_ids = [str(v) for v in payload.get("to_user_ids") if str(v).strip()]
    if "comment_client_safe" in payload and draft.type == "comment":
        draft.comment_client_safe = bool(payload.get("comment_client_safe"))

    draft.save()
    return JsonResponse({"draft": _draft_dict(draft)})


@require_http_methods(["POST"])
def outbound_draft_send_view(request: HttpRequest, org_id, draft_id) -> JsonResponse:
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_membership(
        user, org, allowed_roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
    )
    if membership is None:
        return _json_error("forbidden", status=403)

    draft = OutboundDraft.objects.filter(id=draft_id, org=org).select_related("project").first()
    if draft is None:
        return _json_error("not found", status=404)

    try:
        draft = send_outbound_draft(draft=draft, actor_user=user)
    except OutboundDraftError as exc:
        return _json_error(exc.message, status=400)

    return JsonResponse({"draft": _draft_dict(draft)})
