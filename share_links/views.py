from __future__ import annotations

import json
import uuid

from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from audit.services import write_audit_event
from identity.models import Org, OrgMembership
from reports.models import ReportRun
from reports.services import ReportValidationError

from .models import ShareLink, ShareLinkAccessLog
from .services import create_share_link, default_expires_at, revoke_share_link


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


def _require_authenticated_user(request: HttpRequest):
    if not request.user.is_authenticated:
        return None
    return request.user


def _get_api_key_principal(request: HttpRequest):
    return getattr(request, "api_key_principal", None)


def _principal_has_scope(principal, required: str) -> bool:
    scopes = set(getattr(principal, "scopes", None) or [])
    if required == "read":
        return "read" in scopes or "write" in scopes
    return required in scopes


def _principal_project_id(principal) -> uuid.UUID | None:
    project_id = getattr(principal, "project_id", None)
    if project_id is None or not str(project_id).strip():
        return None
    try:
        return uuid.UUID(str(project_id))
    except (TypeError, ValueError):
        return None


def _require_org(org_id) -> Org | None:
    return Org.objects.filter(id=org_id).first()


def _require_org_access(
    request: HttpRequest,
    org_id,
    *,
    required_scope: str,
    allowed_roles: set[str],
) -> tuple[Org | None, OrgMembership | None, object | None, JsonResponse | None]:
    org = _require_org(org_id)
    if org is None:
        return None, None, None, _json_error("not found", status=404)

    principal = _get_api_key_principal(request)
    if principal is not None:
        if str(org.id) != str(principal.org_id):
            return org, None, principal, _json_error("forbidden", status=403)
        if not _principal_has_scope(principal, required_scope):
            return org, None, principal, _json_error("forbidden", status=403)
        return org, None, principal, None

    user = _require_authenticated_user(request)
    if user is None:
        return org, None, None, _json_error("unauthorized", status=401)

    membership = (
        OrgMembership.objects.filter(user=user, org=org, role__in=allowed_roles)
        .select_related("org")
        .first()
    )
    if membership is None:
        return org, None, None, _json_error("forbidden", status=403)

    return org, membership, None, None


def _created_by_display(share_link: ShareLink) -> dict | None:
    if share_link.created_by_user_id and share_link.created_by_user is not None:
        user = share_link.created_by_user
        display = (user.display_name or "").strip() or user.email
        return {"type": "user", "id": str(user.id), "display": display}
    if share_link.created_by_api_key_id and share_link.created_by_api_key is not None:
        key = share_link.created_by_api_key
        display = str(key.name).strip() or key.prefix
        return {"type": "api_key", "id": str(key.id), "display": display}
    return None


def _share_link_dict(share_link: ShareLink) -> dict:
    return {
        "id": str(share_link.id),
        "org_id": str(share_link.org_id),
        "report_run_id": str(share_link.report_run_id),
        "expires_at": share_link.expires_at.isoformat(),
        "revoked_at": share_link.revoked_at.isoformat() if share_link.revoked_at else None,
        "created_at": share_link.created_at.isoformat(),
        "created_by": _created_by_display(share_link),
        "access_count": int(share_link.access_count or 0),
        "last_access_at": (
            share_link.last_access_at.isoformat() if share_link.last_access_at else None
        ),
    }


def _parse_expires_at(payload: dict) -> tuple[object, JsonResponse | None]:
    raw = payload.get("expires_at")
    if raw is None or not str(raw).strip():
        return default_expires_at(), None

    parsed = parse_datetime(str(raw))
    if parsed is None:
        return None, _json_error("expires_at must be an ISO-8601 datetime string", status=400)

    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())

    if parsed <= timezone.now():
        return None, _json_error("expires_at must be in the future", status=400)

    return parsed, None


@require_http_methods(["POST"])
def publish_share_link_view(request: HttpRequest, org_id, report_run_id) -> JsonResponse:
    org, membership, principal, err = _require_org_access(
        request,
        org_id,
        required_scope="write",
        allowed_roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM},
    )
    if err is not None:
        return err

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    expires_at, expires_err = _parse_expires_at(payload)
    if expires_err is not None:
        return expires_err

    report_run = (
        ReportRun.objects.filter(id=report_run_id, org=org)
        .select_related("project", "template_version")
        .first()
    )
    if report_run is None:
        return _json_error("not found", status=404)

    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None and project_id_restriction != report_run.project_id:
            return _json_error("forbidden", status=403)

    created_by_api_key = getattr(request, "api_key", None) if principal is not None else None

    try:
        share_link, raw_token = create_share_link(
            org=org,
            report_run=report_run,
            expires_at=expires_at,
            created_by_user=request.user if membership is not None else None,
            created_by_api_key=created_by_api_key,
        )
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except ReportValidationError as exc:
        return _json_error(exc.message, status=400)
    except RuntimeError:
        return _json_error("failed to create share link", status=500)

    actor_user = request.user if membership is not None else None
    actor_type = "api_key" if principal is not None else "user"
    actor_id = (
        str(getattr(principal, "api_key_id", None))
        if principal is not None
        else str(actor_user.id)
        if actor_user is not None
        else None
    )

    write_audit_event(
        org=org,
        actor_user=actor_user,
        event_type="report_share_link.published",
        metadata={
            "share_link_id": str(share_link.id),
            "report_run_id": str(report_run.id),
            "expires_at": share_link.expires_at.isoformat(),
            "actor_type": actor_type,
            "actor_id": actor_id,
        },
    )

    share_url = request.build_absolute_uri(f"/p/r/{raw_token}")
    share_link = (
        ShareLink.objects.filter(id=share_link.id)
        .select_related("created_by_user", "created_by_api_key")
        .first()
    )
    return JsonResponse({"share_link": _share_link_dict(share_link), "share_url": share_url})


@require_http_methods(["POST"])
def revoke_share_link_view(request: HttpRequest, org_id, share_link_id) -> JsonResponse:
    org, membership, principal, err = _require_org_access(
        request,
        org_id,
        required_scope="write",
        allowed_roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM},
    )
    if err is not None:
        return err

    share_link = (
        ShareLink.objects.filter(id=share_link_id, org=org)
        .select_related("report_run", "created_by_user", "created_by_api_key")
        .first()
    )
    if share_link is None:
        return _json_error("not found", status=404)

    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if (
            project_id_restriction is not None
            and project_id_restriction != share_link.report_run.project_id
        ):
            return _json_error("forbidden", status=403)

    revoke_share_link(share_link=share_link)

    actor_user = request.user if membership is not None else None
    actor_type = "api_key" if principal is not None else "user"
    actor_id = (
        str(getattr(principal, "api_key_id", None))
        if principal is not None
        else str(actor_user.id)
        if actor_user is not None
        else None
    )

    write_audit_event(
        org=org,
        actor_user=actor_user,
        event_type="report_share_link.revoked",
        metadata={
            "share_link_id": str(share_link.id),
            "report_run_id": str(share_link.report_run_id),
            "actor_type": actor_type,
            "actor_id": actor_id,
        },
    )

    share_link.refresh_from_db()
    return JsonResponse({"share_link": _share_link_dict(share_link)})


@require_http_methods(["GET"])
def share_links_collection_view(request: HttpRequest, org_id) -> JsonResponse:
    org, _membership, principal, err = _require_org_access(
        request,
        org_id,
        required_scope="read",
        allowed_roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM},
    )
    if err is not None:
        return err

    report_run_id_raw = request.GET.get("report_run_id", "").strip()
    report_run_id = None
    if report_run_id_raw:
        try:
            report_run_id = uuid.UUID(report_run_id_raw)
        except (TypeError, ValueError):
            return _json_error("report_run_id must be a UUID", status=400)

    share_links = ShareLink.objects.filter(org=org)
    if report_run_id is not None:
        share_links = share_links.filter(report_run_id=report_run_id)

    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None:
            share_links = share_links.filter(report_run__project_id=project_id_restriction)

    share_links = share_links.select_related("created_by_user", "created_by_api_key").order_by(
        "-created_at"
    )
    return JsonResponse({"share_links": [_share_link_dict(s) for s in share_links]})


@require_http_methods(["GET"])
def share_link_access_logs_view(request: HttpRequest, org_id, share_link_id) -> JsonResponse:
    org, _membership, principal, err = _require_org_access(
        request,
        org_id,
        required_scope="read",
        allowed_roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM},
    )
    if err is not None:
        return err

    share_link = (
        ShareLink.objects.filter(id=share_link_id, org=org).select_related("report_run").first()
    )
    if share_link is None:
        return _json_error("not found", status=404)

    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if (
            project_id_restriction is not None
            and project_id_restriction != share_link.report_run.project_id
        ):
            return _json_error("forbidden", status=403)

    logs = ShareLinkAccessLog.objects.filter(share_link=share_link).order_by("-accessed_at")
    return JsonResponse(
        {
            "access_logs": [
                {
                    "accessed_at": l.accessed_at.isoformat(),
                    "ip_address": l.ip_address,
                    "user_agent": l.user_agent or None,
                }
                for l in logs
            ]
        }
    )
