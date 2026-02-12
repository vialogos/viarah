import json
from datetime import date, timedelta

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
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


@require_http_methods(["POST"])
def create_org_invite_view(request: HttpRequest, org_id) -> JsonResponse:
    """Create an org invite and return its one-time token.

    Auth: Session (ADMIN/PM) for the org (see `docs/api/scope-map.yaml` operation
    `identity__org_invites_post`).
    Inputs: Path `org_id`; JSON body `{email, role}`.
    Returns: Invite metadata plus the raw token and a convenience `invite_url`.
    The `invite_url` is returned as a relative SPA path (not an absolute backend URL) so it can be
    safely used from the frontend origin in local dev and deployments.
    Side effects: Writes `OrgInvite` + audit event(s).
    """
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = get_object_or_404(Org, id=org_id)
    membership = _require_org_role(
        user, org, roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
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
        created_by_user=user,
    )

    write_audit_event(
        org=org,
        actor_user=user,
        event_type="org_invite.created",
        metadata={"invite_id": str(invite.id), "email": invite.email, "role": invite.role},
    )

    invite_url = f"/invite/accept?token={raw_token}"
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


@require_http_methods(["GET"])
def org_memberships_collection_view(request: HttpRequest, org_id) -> JsonResponse:
    """List org memberships (Admin/PM; session-only).

    Auth: Session (ADMIN/PM) for the org (see `docs/api/scope-map.yaml` operation
    `identity__org_memberships_get`).
    Inputs: Path `org_id`; optional query `role`.
    Returns: `{memberships: [...]}` where each membership includes:
      - id, role, user {id, email, display_name}
      - title, skills, bio
      - availability_status, availability_hours_per_week, availability_next_available_at,
        availability_notes
    Side effects: None.
    """
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = Org.objects.filter(id=org_id).first()
    if org is None:
        return _json_error("not found", status=404)

    actor_membership = _require_org_role(
        user, org, roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
    )
    if actor_membership is None:
        return _json_error("forbidden", status=403)

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
            "title": membership.title,
            "skills": list(membership.skills or []),
            "bio": membership.bio,
            "availability_status": membership.availability_status,
            "availability_hours_per_week": membership.availability_hours_per_week,
            "availability_next_available_at": (
                membership.availability_next_available_at.isoformat()
                if membership.availability_next_available_at
                else None
            ),
            "availability_notes": membership.availability_notes,
        }
        for membership in qs
    ]
    return JsonResponse({"memberships": memberships})


@require_http_methods(["PATCH"])
def update_membership_view(request: HttpRequest, org_id, membership_id) -> JsonResponse:
    """Update an org membership's role.

    Auth: Session (ADMIN/PM) for the org (see `docs/api/scope-map.yaml` operation
    `identity__org_membership_patch`).
    Inputs: Path `org_id`, `membership_id`; JSON body supports:
      - role?
      - display_name?
      - title?
      - skills?
      - bio?
      - availability_status?
      - availability_hours_per_week?
      - availability_next_available_at?
      - availability_notes?
    Returns: `{membership}`.
    Side effects: Updates membership role and writes an audit event when the role changes.
    """
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = get_object_or_404(Org, id=org_id)
    actor_membership = _require_org_role(
        user, org, roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
    )
    if actor_membership is None:
        return _json_error("forbidden", status=403)

    membership = get_object_or_404(
        OrgMembership.objects.select_related("org", "user"), id=membership_id, org=org
    )

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    fields_changed: list[str] = []
    membership_update_fields: set[str] = set()

    if "role" in payload:
        role = str(payload.get("role") or "").strip()
        if role not in OrgMembership.Role.values:
            return _json_error("role must be a valid org membership role", status=400)
        old_role = membership.role
        if role != old_role:
            membership.role = role
            membership_update_fields.add("role")
            fields_changed.append("role")
            write_audit_event(
                org=org,
                actor_user=user,
                event_type="org_membership.role_changed",
                metadata={
                    "membership_id": str(membership.id),
                    "old_role": old_role,
                    "new_role": role,
                },
            )

    if "display_name" in payload:
        display_name = str(payload.get("display_name") or "").strip()
        if display_name != getattr(membership.user, "display_name", ""):
            membership.user.display_name = display_name
            membership.user.save(update_fields=["display_name"])
            fields_changed.append("display_name")

    if "title" in payload:
        title = str(payload.get("title") or "").strip()
        if title != (membership.title or ""):
            membership.title = title
            membership_update_fields.add("title")
            fields_changed.append("title")

    if "skills" in payload:
        raw = payload.get("skills")
        if raw is None:
            skills: list[str] = []
        else:
            if not isinstance(raw, list):
                return _json_error("skills must be a list", status=400)
            skills = []
            for item in raw:
                if not isinstance(item, str):
                    return _json_error("skills must be a list of strings", status=400)
                trimmed = item.strip()
                if not trimmed:
                    continue
                skills.append(trimmed)

        seen: set[str] = set()
        deduped: list[str] = []
        for item in skills:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        skills = deduped

        if skills != list(membership.skills or []):
            membership.skills = skills
            membership_update_fields.add("skills")
            fields_changed.append("skills")

    if "bio" in payload:
        bio = str(payload.get("bio") or "").strip()
        if bio != (membership.bio or ""):
            membership.bio = bio
            membership_update_fields.add("bio")
            fields_changed.append("bio")

    if "availability_status" in payload:
        availability_status = str(payload.get("availability_status") or "").strip()
        if availability_status not in OrgMembership.AvailabilityStatus.values:
            return _json_error(
                "availability_status must be a valid availability status", status=400
            )
        if availability_status != membership.availability_status:
            membership.availability_status = availability_status
            membership_update_fields.add("availability_status")
            fields_changed.append("availability_status")

    if "availability_hours_per_week" in payload:
        raw = payload.get("availability_hours_per_week")
        if raw is None or raw == "":
            hours = None
        else:
            if not isinstance(raw, int):
                return _json_error("availability_hours_per_week must be an integer", status=400)
            if raw < 0 or raw > 168:
                return _json_error(
                    "availability_hours_per_week must be between 0 and 168", status=400
                )
            hours = raw

        if hours != membership.availability_hours_per_week:
            membership.availability_hours_per_week = hours
            membership_update_fields.add("availability_hours_per_week")
            fields_changed.append("availability_hours_per_week")

    if "availability_next_available_at" in payload:
        raw = payload.get("availability_next_available_at")
        if raw is None or str(raw).strip() == "":
            next_date = None
        else:
            if not isinstance(raw, str):
                return _json_error(
                    "availability_next_available_at must be a date string", status=400
                )
            try:
                next_date = date.fromisoformat(raw)
            except ValueError:
                return _json_error("availability_next_available_at must be YYYY-MM-DD", status=400)

        if next_date != membership.availability_next_available_at:
            membership.availability_next_available_at = next_date
            membership_update_fields.add("availability_next_available_at")
            fields_changed.append("availability_next_available_at")

    if "availability_notes" in payload:
        availability_notes = str(payload.get("availability_notes") or "").strip()
        if availability_notes != (membership.availability_notes or ""):
            membership.availability_notes = availability_notes
            membership_update_fields.add("availability_notes")
            fields_changed.append("availability_notes")

    if membership_update_fields:
        membership.save(update_fields=sorted(membership_update_fields))

    non_role_changes = [f for f in fields_changed if f != "role"]
    if non_role_changes:
        write_audit_event(
            org=org,
            actor_user=user,
            event_type="org_membership.updated",
            metadata={
                "membership_id": str(membership.id),
                "fields_changed": non_role_changes,
            },
        )

    return JsonResponse({"membership": _membership_dict(membership)})
