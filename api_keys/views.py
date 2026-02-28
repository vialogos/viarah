from __future__ import annotations

import json
import uuid

from django.contrib.auth import get_user_model
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from audit.services import write_audit_event
from identity.models import Org, OrgMembership
from identity.rbac import platform_org_role

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


def _get_membership(user, org: Org) -> OrgMembership | None:
    platform_role = platform_org_role(user)
    if platform_role in {OrgMembership.Role.ADMIN, OrgMembership.Role.PM}:
        return OrgMembership(org=org, user=user, role=platform_role)
    return OrgMembership.objects.filter(user=user, org=org).select_related("org").first()


def _can_manage_all_keys(membership: OrgMembership) -> bool:
    return membership.role in {OrgMembership.Role.ADMIN, OrgMembership.Role.PM}


def _can_self_manage_keys(membership: OrgMembership) -> bool:
    return membership.role in {
        OrgMembership.Role.ADMIN,
        OrgMembership.Role.PM,
        OrgMembership.Role.MEMBER,
    }


def _parse_bool_query(value: str | None) -> bool:
    if value is None:
        return False
    normalized = str(value).strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _api_key_dict(api_key: ApiKey) -> dict:
    return {
        "id": str(api_key.id),
        "org_id": str(api_key.org_id),
        "owner_user_id": str(api_key.owner_user_id),
        "project_id": str(api_key.project_id) if api_key.project_id else None,
        "name": api_key.name,
        "prefix": api_key.prefix,
        "scopes": list(api_key.scopes or []),
        "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
        "last_used_at": api_key.last_used_at.isoformat() if api_key.last_used_at else None,
        "created_by_user_id": (
            str(api_key.created_by_user_id) if api_key.created_by_user_id else None
        ),
        "created_at": api_key.created_at.isoformat(),
        "revoked_at": api_key.revoked_at.isoformat() if api_key.revoked_at else None,
        "rotated_at": api_key.rotated_at.isoformat() if api_key.rotated_at else None,
    }


@require_http_methods(["GET", "POST"])
def api_keys_collection_view(request: HttpRequest) -> JsonResponse:
    """List or create API keys for an org.

    API keys are per-member/user and intended for `viarah-cli` usage.

    Auth: Session.
    Inputs:
      - GET: query `org_id` and optional `mine=1`.
      - POST: JSON `{org_id, name, project_id?, scopes?, owner_user_id?}`.
    Returns:
      - GET `{api_keys: [...]}`.
      - POST `{api_key, token}` (token is returned once).
    """

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
        membership = _get_membership(user, org)
        if membership is None or not _can_self_manage_keys(membership):
            return _json_error("forbidden", status=403)

        mine = _parse_bool_query(request.GET.get("mine"))
        owner_user_id_raw = request.GET.get("owner_user_id")

        keys = ApiKey.objects.filter(org=org).order_by("-created_at")

        if _can_manage_all_keys(membership):
            if mine:
                keys = keys.filter(owner_user=user)
            elif owner_user_id_raw is not None and str(owner_user_id_raw).strip():
                try:
                    owner_user_id = uuid.UUID(str(owner_user_id_raw))
                except (TypeError, ValueError):
                    return _json_error("owner_user_id must be a UUID", status=400)
                keys = keys.filter(owner_user_id=owner_user_id)
        else:
            # Members can only see their own keys.
            keys = keys.filter(owner_user=user)

        return JsonResponse({"api_keys": [_api_key_dict(k) for k in keys]})

    # POST
    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    org_id_raw = str(payload.get("org_id", "")).strip()
    name = str(payload.get("name", "")).strip()
    project_id = payload.get("project_id")
    scopes_raw = payload.get("scopes")
    owner_user_id_raw = payload.get("owner_user_id")

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
    membership = _get_membership(user, org)
    if membership is None or not _can_self_manage_keys(membership):
        return _json_error("forbidden", status=403)

    try:
        scopes = normalize_scopes(scopes_raw)
    except ValueError:
        return _json_error("invalid scopes", status=400)

    owner_user = user
    if owner_user_id_raw is not None and str(owner_user_id_raw).strip():
        if not _can_manage_all_keys(membership):
            return _json_error("forbidden", status=403)

        try:
            owner_uuid = uuid.UUID(str(owner_user_id_raw))
        except (TypeError, ValueError):
            return _json_error("owner_user_id must be a UUID", status=400)

        owner_membership = (
            OrgMembership.objects.filter(org=org, user_id=owner_uuid).select_related("user").first()
        )
        if owner_membership is None:
            return _json_error("owner_user_id must be an org member", status=400)

        owner_user = owner_membership.user

    user_model = get_user_model()
    if not isinstance(owner_user, user_model):
        return _json_error("invalid owner_user", status=400)

    try:
        api_key, minted = create_api_key(
            org=org,
            owner_user=owner_user,
            name=name,
            scopes=scopes,
            project_id=project_id,
            expires_at=None,
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
            "owner_user_id": str(api_key.owner_user_id),
            "project_id": str(api_key.project_id) if api_key.project_id else None,
            "scopes": list(api_key.scopes or []),
            "actor_user_id": str(user.id),
        },
    )

    return JsonResponse({"api_key": _api_key_dict(api_key), "token": minted.token})


def _require_key_manage_access(
    user, api_key: ApiKey
) -> tuple[OrgMembership | None, JsonResponse | None]:
    membership = _get_membership(user, api_key.org)
    if membership is None or not _can_self_manage_keys(membership):
        return None, _json_error("forbidden", status=403)

    if _can_manage_all_keys(membership):
        return membership, None

    if api_key.owner_user_id != user.id:
        return None, _json_error("forbidden", status=403)

    return membership, None


@require_http_methods(["POST"])
def revoke_api_key_view(request: HttpRequest, api_key_id) -> JsonResponse:
    """Revoke an API key.

    Auth: Session.
    Returns: `{api_key}`.
    """

    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    api_key = get_object_or_404(ApiKey.objects.select_related("org"), id=api_key_id)
    membership, err = _require_key_manage_access(user, api_key)
    if err is not None:
        return err

    revoke_api_key(api_key=api_key)

    write_audit_event(
        org=api_key.org,
        actor_user=user,
        event_type="api_key.revoked",
        metadata={
            "key_id": str(api_key.id),
            "key_prefix": api_key.prefix,
            "org_id": str(api_key.org_id),
            "owner_user_id": str(api_key.owner_user_id),
            "actor_user_id": str(user.id),
        },
    )

    return JsonResponse({"api_key": _api_key_dict(api_key)})


@require_http_methods(["POST"])
def rotate_api_key_view(request: HttpRequest, api_key_id) -> JsonResponse:
    """Rotate an API key and return a new token.

    Auth: Session.
    Returns: `{api_key, token}` (token is returned once).
    """

    user = _require_authenticated_user(request)
    if user is None:
        return _json_error("unauthorized", status=401)

    api_key = get_object_or_404(ApiKey.objects.select_related("org"), id=api_key_id)
    membership, err = _require_key_manage_access(user, api_key)
    if err is not None:
        return err

    try:
        minted = rotate_api_key(api_key=api_key)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    write_audit_event(
        org=api_key.org,
        actor_user=user,
        event_type="api_key.rotated",
        metadata={
            "key_id": str(api_key.id),
            "key_prefix": api_key.prefix,
            "org_id": str(api_key.org_id),
            "owner_user_id": str(api_key.owner_user_id),
            "actor_user_id": str(user.id),
        },
    )

    return JsonResponse({"api_key": _api_key_dict(api_key), "token": minted.token})
