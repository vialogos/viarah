import json
from datetime import timedelta

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from audit.services import write_audit_event

from .models import Org, OrgInvite, OrgMembership


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


def _user_dict(user) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": getattr(user, "display_name", ""),
    }


def _membership_dict(membership: OrgMembership) -> dict:
    return {
        "id": str(membership.id),
        "org": {"id": str(membership.org_id), "name": membership.org.name},
        "role": membership.role,
    }


def _get_membership(user, org: Org) -> OrgMembership | None:
    return OrgMembership.objects.filter(user=user, org=org).select_related("org").first()


def _me_payload(user) -> dict:
    if not user.is_authenticated:
        return {"user": None, "memberships": []}

    memberships = (
        OrgMembership.objects.filter(user=user).select_related("org").order_by("created_at")
    )
    return {
        "user": _user_dict(user),
        "memberships": [_membership_dict(m) for m in memberships],
    }


def _require_org_role(user, org: Org, *, roles: set[str] | None = None) -> OrgMembership | None:
    membership = _get_membership(user, org)
    if membership is None:
        return None
    if roles is not None and membership.role not in roles:
        return None
    return membership


@ensure_csrf_cookie
@require_http_methods(["GET"])
def me_view(request: HttpRequest) -> JsonResponse:
    principal = getattr(request, "api_key_principal", None)
    if principal is not None:
        if "read" not in set(principal.scopes or []):
            return _json_error("forbidden", status=403)
        return JsonResponse(
            {
                "principal_type": "api_key",
                "api_key_id": principal.api_key_id,
                "org_id": principal.org_id,
                "project_id": principal.project_id,
                "scopes": list(principal.scopes or []),
                "user": None,
                "memberships": [],
            }
        )

    return JsonResponse(_me_payload(request.user))


@require_http_methods(["POST"])
def login_view(request: HttpRequest) -> JsonResponse:
    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    if not email or not password:
        return _json_error("email and password are required", status=400)

    user = authenticate(request, email=email, password=password)
    if user is None:
        return _json_error("invalid credentials", status=401)

    django_login(request, user)
    return JsonResponse(_me_payload(user))


@require_http_methods(["POST"])
def logout_view(request: HttpRequest) -> HttpResponse:
    django_logout(request)
    return HttpResponse(status=204)


@login_required
@require_http_methods(["POST"])
def create_org_invite_view(request: HttpRequest, org_id) -> JsonResponse:
    org = get_object_or_404(Org, id=org_id)
    membership = _require_org_role(
        request.user, org, roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
    )
    if membership is None:
        return _json_error("forbidden", status=403)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    email = str(payload.get("email", "")).strip().lower()
    role = str(payload.get("role", "")).strip()
    if not email or role not in OrgMembership.Role.values:
        return _json_error("email and valid role are required", status=400)

    raw_token = OrgInvite.new_token()
    invite = OrgInvite.objects.create(
        org=org,
        email=email,
        role=role,
        token_hash=OrgInvite.hash_token(raw_token),
        expires_at=timezone.now() + timedelta(days=7),
        created_by_user=request.user,
    )

    write_audit_event(
        org=org,
        actor_user=request.user,
        event_type="org_invite.created",
        metadata={"invite_id": str(invite.id), "email": invite.email, "role": invite.role},
    )

    invite_url = request.build_absolute_uri(f"/invite/accept?token={raw_token}")
    return JsonResponse(
        {
            "invite": {
                "id": str(invite.id),
                "org_id": str(org.id),
                "email": invite.email,
                "role": invite.role,
                "expires_at": invite.expires_at.isoformat(),
            },
            "token": raw_token,
            "invite_url": invite_url,
        }
    )


@require_http_methods(["POST"])
def accept_invite_view(request: HttpRequest) -> JsonResponse:
    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    token = str(payload.get("token", "")).strip()
    password = str(payload.get("password", ""))
    display_name = str(payload.get("display_name", "")).strip()
    if not token:
        return _json_error("token is required", status=400)

    invite = (
        OrgInvite.objects.select_related("org")
        .filter(
            token_hash=OrgInvite.hash_token(token),
            revoked_at__isnull=True,
            accepted_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .first()
    )
    if invite is None:
        return _json_error("invalid or expired token", status=400)

    email = invite.email.strip().lower()
    user_model = get_user_model()

    if request.user.is_authenticated:
        if request.user.email != email:
            return _json_error("forbidden", status=403)
        user = request.user
    else:
        existing_user = user_model.objects.filter(email=email).first()
        if existing_user is None:
            if not password:
                return _json_error("password is required", status=400)
            user = user_model.objects.create_user(
                email=email, password=password, display_name=display_name
            )
        else:
            if not password:
                return _json_error("password is required", status=400)
            user = authenticate(request, email=email, password=password)
            if user is None:
                return _json_error("invalid credentials", status=401)

    membership, created = OrgMembership.objects.get_or_create(
        org=invite.org,
        user=user,
        defaults={"role": invite.role},
    )

    now = timezone.now()
    invite.accepted_at = now
    invite.save(update_fields=["accepted_at"])

    write_audit_event(
        org=invite.org,
        actor_user=user,
        event_type="org_invite.accepted",
        metadata={
            "invite_id": str(invite.id),
            "email": invite.email,
            "role": invite.role,
            "membership_id": str(membership.id),
            "membership_created": created,
        },
    )

    if created:
        write_audit_event(
            org=invite.org,
            actor_user=user,
            event_type="org_membership.created",
            metadata={"membership_id": str(membership.id), "role": membership.role},
        )

    django_login(request, user)
    return JsonResponse({"membership": _membership_dict(membership)})


@login_required
@require_http_methods(["PATCH"])
def update_membership_view(request: HttpRequest, org_id, membership_id) -> JsonResponse:
    org = get_object_or_404(Org, id=org_id)
    actor_membership = _require_org_role(
        request.user, org, roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
    )
    if actor_membership is None:
        return _json_error("forbidden", status=403)

    membership = get_object_or_404(
        OrgMembership.objects.select_related("org"), id=membership_id, org=org
    )

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    role = str(payload.get("role", "")).strip()
    if role not in OrgMembership.Role.values:
        return _json_error("valid role is required", status=400)

    old_role = membership.role
    if role != old_role:
        membership.role = role
        membership.save(update_fields=["role"])
        write_audit_event(
            org=org,
            actor_user=request.user,
            event_type="org_membership.role_changed",
            metadata={
                "membership_id": str(membership.id),
                "old_role": old_role,
                "new_role": role,
            },
        )

    return JsonResponse({"membership": _membership_dict(membership)})
