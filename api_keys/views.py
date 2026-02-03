from __future__ import annotations

import json
import uuid

from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from audit.services import write_audit_event
from identity.models import Org, OrgMembership

from .models import ApiKey
from .services import create_api_key, normalize_scopes, revoke_api_key, rotate_api_key


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


def _require_org_role(user, org: Org, *, roles: set[str]) -> OrgMembership | None:
    return (
        OrgMembership.objects.filter(user=user, org=org, role__in=roles)
        .select_related("org")
        .first()
    )


def _api_key_dict(api_key: ApiKey) -> dict:
    return {
        "id": str(api_key.id),
        "org_id": str(api_key.org_id),
        "project_id": str(api_key.project_id) if api_key.project_id else None,
        "name": api_key.name,
        "prefix": api_key.prefix,
        "scopes": list(api_key.scopes or []),
        "created_by_user_id": (
            str(api_key.created_by_user_id) if api_key.created_by_user_id else None
        ),
        "created_at": api_key.created_at.isoformat(),
        "revoked_at": api_key.revoked_at.isoformat() if api_key.revoked_at else None,
        "rotated_at": api_key.rotated_at.isoformat() if api_key.rotated_at else None,
    }


@require_http_methods(["GET", "POST"])
def api_keys_collection_view(request: HttpRequest) -> JsonResponse:
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    if request.method == "GET":
        org_id_raw = request.GET.get("org_id", "").strip()
        if not org_id_raw:
            return _json_error("org_id is required", status=400)

        try:
            org_id = uuid.UUID(org_id_raw)
        except (TypeError, ValueError):
            return _json_error("org_id must be a UUID", status=400)

        org = get_object_or_404(Org, id=org_id)
        membership = _require_org_role(
            user, org, roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
        )
        if membership is None:
            return _json_error("forbidden", status=403)

        keys = ApiKey.objects.filter(org=org).order_by("-created_at")
        return JsonResponse({"api_keys": [_api_key_dict(k) for k in keys]})

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    org_id_raw = str(payload.get("org_id", "")).strip()
    name = str(payload.get("name", "")).strip()
    project_id = payload.get("project_id")
    scopes_raw = payload.get("scopes")

    if not org_id_raw:
        return _json_error("org_id is required", status=400)
    if not name:
        return _json_error("name is required", status=400)
    if scopes_raw is not None and not isinstance(scopes_raw, list):
        return _json_error("scopes must be a list", status=400)

    try:
        org_id = uuid.UUID(org_id_raw)
    except (TypeError, ValueError):
        return _json_error("org_id must be a UUID", status=400)

    if project_id is not None:
        try:
            project_id = uuid.UUID(str(project_id))
        except (TypeError, ValueError):
            return _json_error("project_id must be a UUID", status=400)

    org = get_object_or_404(Org, id=org_id)
    membership = _require_org_role(
        user, org, roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
    )
    if membership is None:
        return _json_error("forbidden", status=403)

    try:
        scopes = normalize_scopes(scopes_raw)
    except ValueError:
        return _json_error("invalid scopes", status=400)

    try:
        api_key, minted = create_api_key(
            org=org,
            name=name,
            scopes=scopes,
            project_id=project_id,
            created_by_user=user,
        )
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    write_audit_event(
        org=org,
        actor_user=user,
        event_type="api_key.created",
        metadata={
            "key_id": str(api_key.id),
            "key_prefix": api_key.prefix,
            "org_id": str(org.id),
            "project_id": str(api_key.project_id) if api_key.project_id else None,
            "scopes": list(api_key.scopes or []),
            "actor_user_id": str(user.id),
        },
    )

    return JsonResponse({"api_key": _api_key_dict(api_key), "token": minted.token})


@require_http_methods(["POST"])
def revoke_api_key_view(request: HttpRequest, api_key_id) -> JsonResponse:
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    api_key = get_object_or_404(ApiKey.objects.select_related("org"), id=api_key_id)
    org = api_key.org
    membership = _require_org_role(
        user, org, roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
    )
    if membership is None:
        return _json_error("forbidden", status=403)

    revoke_api_key(api_key=api_key)

    write_audit_event(
        org=org,
        actor_user=user,
        event_type="api_key.revoked",
        metadata={
            "key_id": str(api_key.id),
            "key_prefix": api_key.prefix,
            "org_id": str(org.id),
            "actor_user_id": str(user.id),
        },
    )

    return JsonResponse({"api_key": _api_key_dict(api_key)})


@require_http_methods(["POST"])
def rotate_api_key_view(request: HttpRequest, api_key_id) -> JsonResponse:
    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    api_key = get_object_or_404(ApiKey.objects.select_related("org"), id=api_key_id)
    org = api_key.org
    membership = _require_org_role(
        user, org, roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
    )
    if membership is None:
        return _json_error("forbidden", status=403)

    try:
        minted = rotate_api_key(api_key=api_key)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    write_audit_event(
        org=org,
        actor_user=user,
        event_type="api_key.rotated",
        metadata={
            "key_id": str(api_key.id),
            "key_prefix": api_key.prefix,
            "org_id": str(org.id),
            "actor_user_id": str(user.id),
        },
    )

    return JsonResponse({"api_key": _api_key_dict(api_key), "token": minted.token})
