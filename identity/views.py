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


def _require_session_user(request: HttpRequest):
    if getattr(request, "api_key_principal", None) is not None:
        return None, _json_error("forbidden", status=403)
    if not request.user.is_authenticated:
        return None, _json_error("unauthorized", status=401)
    return request.user, None


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
    """Return the current session user or API key principal context.

    Auth: Public/session/API key (see `docs/api/scope-map.yaml` operation `identity__me_get`).
    Returns: `{user, memberships}` for sessions.
    API key principals receive `{principal_type, scopes, ...}`.
    Side effects: Ensures a CSRF cookie is set for browser-based session flows.
    """
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
    """Authenticate email/password and create a session cookie.

    Auth: Public (see `docs/api/scope-map.yaml` operation `identity__auth_login_post`).
    Inputs: JSON body `{email, password}`.
    Returns: Current user payload `{user, memberships}`.
    Side effects: Logs the user in via Django session authentication.
    """
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
    """Log out the current session (safe to call when already logged out).

    Auth: Typically session-authenticated (see `docs/api/scope-map.yaml` operation
    `identity__auth_logout_post`).
    Returns: 204 No Content.
    Side effects: Clears the Django session for the current request.
    """
    django_logout(request)
    return HttpResponse(status=204)


@login_required
@require_http_methods(["POST"])
def create_org_invite_view(request: HttpRequest, org_id) -> JsonResponse:
    """Create an org invite and return its one-time token.

    Auth: Session (ADMIN/PM) for the org (see `docs/api/scope-map.yaml` operation
    `identity__org_invites_post`).
    Inputs: Path `org_id`; JSON body `{email, role}`.
    Returns: Invite metadata plus the raw token and a convenience `invite_url`.
    Side effects: Writes `OrgInvite` + audit event(s).
    """
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
    """Accept an org invite token and ensure the user has org membership.

    Auth: Public or session (see `docs/api/scope-map.yaml` operation
    `identity__invites_accept_post`).
    Inputs: JSON body `{token, password?, display_name?}`.
    Returns: `{membership}`.
    Side effects: May create a user, creates membership if missing, marks invite accepted,
    writes audit events, and logs the user in to a session.
    """
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

            if existing_user.has_usable_password():
                user = authenticate(request, email=email, password=password)
                if user is None:
                    return _json_error("invalid credentials", status=401)
            else:
                if display_name and not getattr(existing_user, "display_name", "").strip():
                    existing_user.display_name = display_name
                existing_user.set_password(password)
                existing_user.save(update_fields=["display_name", "password"])
                user = existing_user

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


@require_http_methods(["GET", "POST"])
def org_memberships_collection_view(request: HttpRequest, org_id) -> JsonResponse:
    """List or provision org memberships (Admin/PM; session-only).

    Auth: Session (ADMIN/PM) for the org (see `docs/api/scope-map.yaml` operation
    `identity__org_memberships_get`).
    Inputs: Path `org_id`; optional query `role`.
    Returns: GET `{memberships: [{id, role, user: {id, email, display_name}}]}`.
    Side effects: POST may create a user (with unusable password) and/or create a membership.
    """
    org = Org.objects.filter(id=org_id).first()
    if org is None:
        return _json_error("not found", status=404)

    principal = getattr(request, "api_key_principal", None)
    api_key = getattr(request, "api_key", None)
    if principal is not None:
        if str(org.id) != str(getattr(principal, "org_id", "")):
            return _json_error("forbidden", status=403)

        project_id = getattr(principal, "project_id", None)
        if project_id:
            return _json_error("forbidden", status=403)

        scopes = set(getattr(principal, "scopes", None) or [])
        required_scope = "read" if request.method == "GET" else "write"
        if required_scope == "read":
            if "read" not in scopes and "write" not in scopes:
                return _json_error("forbidden", status=403)
        else:
            if "write" not in scopes:
                return _json_error("forbidden", status=403)

        actor_user = getattr(api_key, "created_by_user", None)
        session_user = None
    else:
        session_user, err = _require_session_user(request)
        if err is not None:
            return err

        actor_membership = _require_org_role(
            session_user, org, roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
        )
        if actor_membership is None:
            return _json_error("forbidden", status=403)
        actor_user = session_user

    if request.method == "POST":
        try:
            payload = _parse_json(request)
        except ValueError as exc:
            return _json_error(str(exc), status=400)

        email = str(payload.get("email", "")).strip().lower()
        role = str(payload.get("role", "")).strip() or OrgMembership.Role.MEMBER
        display_name = str(payload.get("display_name", "")).strip()
        if not email:
            return _json_error("email is required", status=400)
        if principal is not None:
            role = OrgMembership.Role.MEMBER
        if role not in OrgMembership.Role.values:
            return _json_error("valid role is required", status=400)

        user_model = get_user_model()
        target_user = user_model.objects.filter(email=email).first()
        user_created = False
        if target_user is None:
            target_user = user_model.objects.create_user(
                email=email, password=None, display_name=display_name
            )
            user_created = True
        else:
            if display_name and not getattr(target_user, "display_name", "").strip():
                target_user.display_name = display_name
                target_user.save(update_fields=["display_name"])

        membership, membership_created = OrgMembership.objects.get_or_create(
            org=org,
            user=target_user,
            defaults={"role": role},
        )
        if membership_created:
            write_audit_event(
                org=org,
                actor_user=actor_user,
                event_type="org_membership.created",
                metadata={
                    "membership_id": str(membership.id),
                    "role": membership.role,
                    "source": "provision",
                },
            )

        membership_payload = {
            "id": str(membership.id),
            "role": membership.role,
            "user": _user_dict(target_user),
        }
        status = 201 if user_created or membership_created else 200
        return JsonResponse(
            {
                "membership": membership_payload,
                "user_created": user_created,
                "membership_created": membership_created,
            },
            status=status,
        )

    qs = OrgMembership.objects.filter(org=org).select_related("user").order_by("created_at")

    role = request.GET.get("role")
    if role is not None and str(role).strip():
        role = str(role).strip()
        if role not in OrgMembership.Role.values:
            return _json_error("role must be a valid org membership role", status=400)
        qs = qs.filter(role=role)

    memberships = [
        {
            "id": str(membership.id),
            "role": membership.role,
            "user": _user_dict(membership.user),
        }
        for membership in qs
    ]
    return JsonResponse({"memberships": memberships})


@login_required
@require_http_methods(["PATCH"])
def update_membership_view(request: HttpRequest, org_id, membership_id) -> JsonResponse:
    """Update an org membership's role.

    Auth: Session (ADMIN/PM) for the org (see `docs/api/scope-map.yaml` operation
    `identity__org_membership_patch`).
    Inputs: Path `org_id`, `membership_id`; JSON body `{role}`.
    Returns: `{membership}`.
    Side effects: Updates membership role and writes an audit event when the role changes.
    """
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
