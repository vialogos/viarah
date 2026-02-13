import json
import uuid
from datetime import date, datetime, time, timedelta

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.db import IntegrityError, models
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from audit.services import write_audit_event

from .availability import ExceptionWindow, WeeklyWindow, summarize_availability
from .models import (
    Org,
    OrgInvite,
    OrgMembership,
    Person,
    PersonAvailabilityException,
    PersonAvailabilityWeeklyWindow,
)


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
        user_model = get_user_model()
        owner = user_model.objects.filter(id=principal.owner_user_id).first()
        if owner is None:
            return _json_error("forbidden", status=403)

        membership = (
            OrgMembership.objects.filter(user=owner, org_id=principal.org_id)
            .select_related("org")
            .first()
        )
        if membership is None:
            return _json_error("forbidden", status=403)

        return JsonResponse(
            {
                "principal_type": "api_key",
                "api_key_id": principal.api_key_id,
                "org_id": principal.org_id,
                "owner_user_id": principal.owner_user_id,
                "project_id": principal.project_id,
                "scopes": list(principal.scopes or []),
                "user": _user_dict(owner),
                "memberships": [_membership_dict(membership)],
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


def _person_summary_dict(person: Person) -> dict:
    display = (person.preferred_name or person.full_name or person.email or "").strip()
    return {
        "id": str(person.id),
        "display": display,
        "email": person.email,
    }


def _invite_status(invite: OrgInvite) -> str:
    if invite.accepted_at is not None:
        return "accepted"
    if invite.revoked_at is not None:
        return "revoked"
    if invite.expires_at <= timezone.now():
        return "expired"
    return "active"


def _invite_dict(invite: OrgInvite) -> dict:
    return {
        "id": str(invite.id),
        "org_id": str(invite.org_id),
        "person_id": str(invite.person_id) if invite.person_id else None,
        "person": _person_summary_dict(invite.person) if getattr(invite, "person", None) else None,
        "email": invite.email,
        "role": invite.role,
        "message": invite.message,
        "status": _invite_status(invite),
        "expires_at": invite.expires_at.isoformat(),
        "created_by_user_id": str(invite.created_by_user_id),
        "created_at": invite.created_at.isoformat(),
        "accepted_at": invite.accepted_at.isoformat() if invite.accepted_at else None,
        "revoked_at": invite.revoked_at.isoformat() if invite.revoked_at else None,
    }


def _person_dict(
    *,
    person: Person,
    membership_role_by_user_id: dict[str, str],
    active_invite_by_person_id: dict[str, OrgInvite],
) -> dict:
    active_invite = active_invite_by_person_id.get(str(person.id))
    membership_role = (
        membership_role_by_user_id.get(str(person.user_id)) if person.user_id else None
    )

    if person.user_id and membership_role:
        status = "active"
    elif active_invite is not None:
        status = "invited"
    else:
        status = "candidate"

    user_payload = None
    if getattr(person, "user", None) is not None and person.user_id:
        user_payload = _user_dict(person.user)

    return {
        "id": str(person.id),
        "org_id": str(person.org_id),
        "user": user_payload,
        "status": status,
        "membership_role": membership_role,
        "full_name": person.full_name,
        "preferred_name": person.preferred_name,
        "email": person.email,
        "title": person.title,
        "skills": list(person.skills or []),
        "bio": person.bio,
        "notes": person.notes,
        "timezone": person.timezone,
        "location": person.location,
        "phone": person.phone,
        "slack_handle": person.slack_handle,
        "linkedin_url": person.linkedin_url,
        "created_at": person.created_at.isoformat(),
        "updated_at": person.updated_at.isoformat(),
        "active_invite": _invite_dict(active_invite) if active_invite is not None else None,
    }


@require_http_methods(["GET", "POST"])
def org_people_collection_view(request: HttpRequest, org_id) -> JsonResponse:
    """List or create People records for an org (PM/admin; session-only).

    Auth: Session (ADMIN/PM) for the org.
    Inputs:
      - GET: optional query `q`.
      - POST: JSON `{full_name?, preferred_name?, email?, title?, skills?, bio?, notes?,`
        `timezone?, ...}`.
    Returns:
      - GET `{people: [...]}`.
      - POST `{person}`.
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

    if request.method == "GET":
        qs = (
            Person.objects.filter(org=org)
            .select_related("user")
            .order_by("full_name", "preferred_name", "created_at")
        )
        q = request.GET.get("q")
        if q is not None and str(q).strip():
            needle = str(q).strip()
            qs = qs.filter(
                models.Q(full_name__icontains=needle)
                | models.Q(preferred_name__icontains=needle)
                | models.Q(email__icontains=needle)
            )

        people = list(qs)

        user_ids = [p.user_id for p in people if p.user_id]
        membership_role_by_user_id = {
            str(m.user_id): m.role
            for m in OrgMembership.objects.filter(org=org, user_id__in=user_ids).only(
                "user_id", "role"
            )
        }

        person_ids = [p.id for p in people]
        invites = (
            OrgInvite.objects.filter(
                org=org,
                person_id__in=person_ids,
                accepted_at__isnull=True,
                revoked_at__isnull=True,
                expires_at__gt=timezone.now(),
            )
            .select_related("person")
            .order_by("-created_at")
        )
        active_invite_by_person_id: dict[str, OrgInvite] = {}
        for invite in invites:
            pid = str(invite.person_id)
            if pid not in active_invite_by_person_id:
                active_invite_by_person_id[pid] = invite

        return JsonResponse(
            {
                "people": [
                    _person_dict(
                        person=p,
                        membership_role_by_user_id=membership_role_by_user_id,
                        active_invite_by_person_id=active_invite_by_person_id,
                    )
                    for p in people
                ]
            }
        )

    # POST
    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    email_raw = payload.get("email")
    email: str | None
    if email_raw is None:
        email = None
    else:
        email = str(email_raw).strip().lower() or None

    if email is not None and Person.objects.filter(org=org, email=email).exists():
        return _json_error("person already exists", status=400)

    full_name = str(payload.get("full_name") or "").strip()
    preferred_name = str(payload.get("preferred_name") or "").strip()

    if not full_name and not preferred_name and not email:
        return _json_error(
            "at least one of full_name, preferred_name, or email is required", status=400
        )

    user_model = get_user_model()
    linked_user = None
    if email:
        linked_user = user_model.objects.filter(email=email).first()
        if (
            linked_user is not None
            and OrgMembership.objects.filter(org=org, user=linked_user).exists()
        ):
            if Person.objects.filter(org=org, user=linked_user).exists():
                return _json_error("person already exists", status=400)

    skills_raw = payload.get("skills")
    skills: list[str] = []
    if skills_raw is not None:
        if not isinstance(skills_raw, list):
            return _json_error("skills must be a list of strings", status=400)
        for item in skills_raw:
            if not isinstance(item, str):
                return _json_error("skills must be a list of strings", status=400)
            trimmed = item.strip()
            if trimmed and trimmed not in skills:
                skills.append(trimmed)

    person = Person.objects.create(
        org=org,
        user=linked_user,
        email=email,
        full_name=full_name,
        preferred_name=preferred_name,
        title=str(payload.get("title") or "").strip(),
        skills=skills,
        bio=str(payload.get("bio") or "").strip(),
        notes=str(payload.get("notes") or "").strip(),
        timezone=str(payload.get("timezone") or "").strip() or "UTC",
        location=str(payload.get("location") or "").strip(),
        phone=str(payload.get("phone") or "").strip(),
        slack_handle=str(payload.get("slack_handle") or "").strip(),
        linkedin_url=str(payload.get("linkedin_url") or "").strip(),
    )

    return JsonResponse(
        {
            "person": _person_dict(
                person=person,
                membership_role_by_user_id={},
                active_invite_by_person_id={},
            )
        }
    )


@require_http_methods(["GET", "PATCH"])
def person_detail_view(request: HttpRequest, org_id, person_id) -> JsonResponse:
    """Get or update a Person record (PM/admin; session-only)."""

    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = get_object_or_404(Org, id=org_id)
    actor_membership = _require_org_role(
        user, org, roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
    )
    if actor_membership is None:
        return _json_error("forbidden", status=403)

    person = get_object_or_404(Person.objects.select_related("user"), id=person_id, org=org)

    membership_role_by_user_id: dict[str, str] = {}
    if person.user_id:
        role = (
            OrgMembership.objects.filter(org=org, user_id=person.user_id)
            .values_list("role", flat=True)
            .first()
        )
        if role:
            membership_role_by_user_id[str(person.user_id)] = str(role)

    active_invite_by_person_id: dict[str, OrgInvite] = {}
    active_invite = (
        OrgInvite.objects.filter(
            org=org,
            person=person,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .select_related("person")
        .order_by("-created_at")
        .first()
    )
    if active_invite is not None:
        active_invite_by_person_id[str(person.id)] = active_invite

    if request.method == "GET":
        return JsonResponse(
            {
                "person": _person_dict(
                    person=person,
                    membership_role_by_user_id=membership_role_by_user_id,
                    active_invite_by_person_id=active_invite_by_person_id,
                )
            }
        )

    # PATCH
    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    fields_to_update: set[str] = set()

    for field in [
        "full_name",
        "preferred_name",
        "title",
        "bio",
        "notes",
        "timezone",
        "location",
        "phone",
        "slack_handle",
        "linkedin_url",
    ]:
        if field in payload:
            setattr(person, field, str(payload.get(field) or "").strip())
            fields_to_update.add(field)

    if "email" in payload:
        raw = payload.get("email")
        if raw is None or str(raw).strip() == "":
            person.email = None
        else:
            person.email = str(raw).strip().lower()
        fields_to_update.add("email")

    if "skills" in payload:
        raw = payload.get("skills")
        if raw is None:
            skills = []
        else:
            if not isinstance(raw, list):
                return _json_error("skills must be a list of strings", status=400)
            skills = []
            for item in raw:
                if not isinstance(item, str):
                    return _json_error("skills must be a list of strings", status=400)
                trimmed = item.strip()
                if trimmed and trimmed not in skills:
                    skills.append(trimmed)
        person.skills = skills
        fields_to_update.add("skills")

    if fields_to_update:
        person.save(update_fields=sorted(fields_to_update | {"updated_at"}))

    return JsonResponse(
        {
            "person": _person_dict(
                person=person,
                membership_role_by_user_id=membership_role_by_user_id,
                active_invite_by_person_id=active_invite_by_person_id,
            )
        }
    )


@require_http_methods(["GET"])
def person_project_memberships_view(request: HttpRequest, org_id, person_id) -> JsonResponse:
    """List project memberships for a Person (PM/admin; session-only).

    Notes
    - Only active members (a Person linked to a User + org membership) can be added to projects.
      Candidates/invited people have no linked User yet, so this returns an empty list for them.
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

    person = get_object_or_404(Person, id=person_id, org=org)
    if not person.user_id:
        return JsonResponse({"memberships": []})

    from work_items.models import ProjectMembership

    memberships = (
        ProjectMembership.objects.filter(user_id=person.user_id, project__org=org)
        .select_related("project")
        .order_by("project__name", "created_at")
    )

    return JsonResponse(
        {
            "memberships": [
                {
                    "id": str(m.id),
                    "project": {
                        "id": str(m.project_id),
                        "workflow_id": str(m.project.workflow_id)
                        if getattr(m, "project", None) and m.project.workflow_id
                        else None,
                        "name": m.project.name if getattr(m, "project", None) else "",
                    },
                    "created_at": m.created_at.isoformat(),
                }
                for m in memberships
            ]
        }
    )


@require_http_methods(["POST"])
def person_invite_view(request: HttpRequest, org_id, person_id) -> JsonResponse:
    """Create an org invite for a Person (PM/admin; session-only).

    Inputs: JSON `{role, email?, message?}`. If `email` is omitted, uses `Person.email`.
    Returns: `{invite, token, invite_url}`.
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

    person = get_object_or_404(Person, id=person_id, org=org)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    role = str(payload.get("role", "")).strip()
    if role not in OrgMembership.Role.values:
        return _json_error("role must be a valid org membership role", status=400)

    email = str(payload.get("email") or "").strip().lower() or (person.email or "")
    email = email.strip().lower()
    if not email:
        return _json_error("email is required", status=400)

    if person.email is None or person.email.strip() != email:
        person.email = email
        person.save(update_fields=["email", "updated_at"])

    message = str(payload.get("message") or "").strip()

    raw_token = OrgInvite.new_token()
    invite = OrgInvite.objects.create(
        org=org,
        person=person,
        email=email,
        role=role,
        message=message,
        token_hash=OrgInvite.hash_token(raw_token),
        expires_at=timezone.now() + timedelta(days=7),
        created_by_user=user,
    )

    write_audit_event(
        org=org,
        actor_user=user,
        event_type="org_invite.created",
        metadata={
            "invite_id": str(invite.id),
            "person_id": str(person.id),
            "email": invite.email,
            "role": invite.role,
        },
    )

    invite_url = f"/invite/accept?token={raw_token}"
    return JsonResponse(
        {
            "invite": _invite_dict(invite),
            "token": raw_token,
            "invite_url": invite_url,
        }
    )


@require_http_methods(["GET", "POST"])
def org_invites_collection_view(request: HttpRequest, org_id) -> JsonResponse:
    """List or create org invites (PM/admin; session-only)."""

    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = get_object_or_404(Org, id=org_id)
    actor_membership = _require_org_role(
        user, org, roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
    )
    if actor_membership is None:
        return _json_error("forbidden", status=403)

    if request.method == "GET":
        qs = OrgInvite.objects.filter(org=org).select_related("person").order_by("-created_at")
        status = request.GET.get("status")
        if status is not None and str(status).strip():
            status_val = str(status).strip().lower()
            now = timezone.now()
            if status_val == "active":
                qs = qs.filter(
                    accepted_at__isnull=True, revoked_at__isnull=True, expires_at__gt=now
                )
            elif status_val == "accepted":
                qs = qs.filter(accepted_at__isnull=False)
            elif status_val == "revoked":
                qs = qs.filter(revoked_at__isnull=False)
            elif status_val == "expired":
                qs = qs.filter(
                    accepted_at__isnull=True, revoked_at__isnull=True, expires_at__lte=now
                )
            else:
                return _json_error("invalid status", status=400)

        return JsonResponse({"invites": [_invite_dict(i) for i in qs]})

    # POST (legacy-friendly: supports person_id or email)
    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    role = str(payload.get("role", "")).strip()
    if role not in OrgMembership.Role.values:
        return _json_error("role must be a valid org membership role", status=400)

    person = None
    raw_person_id = payload.get("person_id")
    if raw_person_id is not None and str(raw_person_id).strip():
        try:
            person_uuid = uuid.UUID(str(raw_person_id))
        except (TypeError, ValueError):
            return _json_error("person_id must be a UUID", status=400)
        person = Person.objects.filter(id=person_uuid, org=org).first()
        if person is None:
            return _json_error("person not found", status=404)

    email_raw = payload.get("email")
    email: str | None
    if email_raw is None:
        email = None
    else:
        email = str(email_raw).strip().lower() or None

    if person is None:
        if not email:
            return _json_error("email is required", status=400)
        person = Person.objects.filter(org=org, email=email).first()
        if person is None:
            person = Person.objects.create(
                org=org,
                email=email,
                full_name=str(payload.get("full_name") or "").strip(),
            )

    invite_email = email or person.email
    if invite_email is None:
        return _json_error("email is required", status=400)

    message = str(payload.get("message") or "").strip()

    raw_token = OrgInvite.new_token()
    invite = OrgInvite.objects.create(
        org=org,
        person=person,
        email=invite_email,
        role=role,
        message=message,
        token_hash=OrgInvite.hash_token(raw_token),
        expires_at=timezone.now() + timedelta(days=7),
        created_by_user=user,
    )

    write_audit_event(
        org=org,
        actor_user=user,
        event_type="org_invite.created",
        metadata={
            "invite_id": str(invite.id),
            "person_id": str(person.id),
            "email": invite.email,
            "role": invite.role,
        },
    )

    invite_url = f"/invite/accept?token={raw_token}"
    return JsonResponse(
        {
            "invite": _invite_dict(invite),
            "token": raw_token,
            "invite_url": invite_url,
        }
    )


@require_http_methods(["POST"])
def org_invite_revoke_view(request: HttpRequest, org_id, invite_id) -> JsonResponse:
    """Revoke an org invite (PM/admin; session-only; idempotent)."""

    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = get_object_or_404(Org, id=org_id)
    actor_membership = _require_org_role(
        user, org, roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
    )
    if actor_membership is None:
        return _json_error("forbidden", status=403)

    invite = get_object_or_404(OrgInvite.objects.select_related("person"), id=invite_id, org=org)

    if invite.revoked_at is None:
        invite.revoked_at = timezone.now()
        invite.save(update_fields=["revoked_at"])
        write_audit_event(
            org=org,
            actor_user=user,
            event_type="org_invite.revoked",
            metadata={
                "invite_id": str(invite.id),
                "person_id": str(invite.person_id) if invite.person_id else None,
            },
        )

    return JsonResponse({"invite": _invite_dict(invite)})


@require_http_methods(["POST"])
def org_invite_resend_view(request: HttpRequest, org_id, invite_id) -> JsonResponse:
    """Resend/regenerate an invite link by minting a new token (PM/admin; session-only)."""

    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = get_object_or_404(Org, id=org_id)
    actor_membership = _require_org_role(
        user, org, roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM}
    )
    if actor_membership is None:
        return _json_error("forbidden", status=403)

    invite = get_object_or_404(OrgInvite.objects.select_related("person"), id=invite_id, org=org)

    if invite.accepted_at is not None:
        return _json_error("cannot resend an accepted invite", status=400)

    if invite.person is None:
        person = Person.objects.filter(org=org, email=invite.email).first()
        if person is None:
            person = Person.objects.create(org=org, email=invite.email)
        invite.person = person
        invite.save(update_fields=["person"])

    if invite.revoked_at is None:
        invite.revoked_at = timezone.now()
        invite.save(update_fields=["revoked_at"])

    raw_token = OrgInvite.new_token()
    new_invite = OrgInvite.objects.create(
        org=org,
        person=invite.person,
        email=invite.email,
        role=invite.role,
        message=invite.message,
        token_hash=OrgInvite.hash_token(raw_token),
        expires_at=timezone.now() + timedelta(days=7),
        created_by_user=user,
    )

    write_audit_event(
        org=org,
        actor_user=user,
        event_type="org_invite.resent",
        metadata={
            "invite_id": str(new_invite.id),
            "prior_invite_id": str(invite.id),
            "person_id": str(new_invite.person_id),
            "email": new_invite.email,
            "role": new_invite.role,
        },
    )

    invite_url = f"/invite/accept?token={raw_token}"
    return JsonResponse(
        {
            "invite": _invite_dict(new_invite),
            "token": raw_token,
            "invite_url": invite_url,
        }
    )


@require_http_methods(["POST"])
def accept_invite_view_v2(request: HttpRequest) -> JsonResponse:
    """Accept an org invite token and ensure the user has org membership.

    This variant also links/creates a `Person` record and associates it to the accepting user.

    Auth: Public or session.
    Inputs: JSON body `{token, password?, display_name?}`.
    Returns: `{membership, person, needs_profile_setup}`.
    Side effects: May create a user, creates membership if missing, marks invite accepted,
    links person <-> user, writes audit events, and logs the user in to a session.
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
        OrgInvite.objects.select_related("org", "person")
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

    person = invite.person
    if person is None:
        person = Person.objects.filter(org=invite.org, email=email).first()
        if person is None:
            person = Person.objects.create(
                org=invite.org,
                email=email,
                preferred_name=display_name,
            )
        invite.person = person
        invite.save(update_fields=["person"])

    if person.email is None:
        person.email = email

    if person.user_id is None:
        person.user = user

    if (
        display_name
        and not (person.preferred_name or "").strip()
        and not (person.full_name or "").strip()
    ):
        person.preferred_name = display_name

    person.save(update_fields=["email", "user", "preferred_name", "updated_at"])

    invite.accepted_at = timezone.now()
    invite.save(update_fields=["accepted_at"])

    write_audit_event(
        org=invite.org,
        actor_user=user,
        event_type="org_invite.accepted",
        metadata={
            "invite_id": str(invite.id),
            "person_id": str(person.id),
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

    if not (getattr(user, "display_name", "") or "").strip():
        preferred = (person.preferred_name or person.full_name or "").strip()
        if preferred:
            user.display_name = preferred
            user.save(update_fields=["display_name"])

    needs_profile_setup = not (person.timezone or "").strip() or not (person.skills or [])

    django_login(request, user)
    return JsonResponse(
        {
            "membership": _membership_dict(membership),
            "person": _person_summary_dict(person),
            "needs_profile_setup": bool(needs_profile_setup),
        }
    )


# === Person availability schedule (weekly + exceptions) ===


def _weekly_window_dict(window: PersonAvailabilityWeeklyWindow) -> dict:
    return {
        "id": str(window.id),
        "weekday": int(window.weekday),
        "start_time": window.start_time.isoformat(timespec="minutes"),
        "end_time": window.end_time.isoformat(timespec="minutes"),
        "created_at": window.created_at.isoformat(),
        "updated_at": window.updated_at.isoformat(),
    }


def _availability_exception_dict(exc: PersonAvailabilityException) -> dict:
    return {
        "id": str(exc.id),
        "kind": str(exc.kind),
        "starts_at": exc.starts_at.isoformat(),
        "ends_at": exc.ends_at.isoformat(),
        "title": exc.title,
        "notes": exc.notes,
        "created_by_user_id": str(exc.created_by_user_id),
        "created_at": exc.created_at.isoformat(),
        "updated_at": exc.updated_at.isoformat(),
    }


def _require_person_schedule_access(
    request: HttpRequest, org_id, person_id
) -> tuple[object | None, Org | None, OrgMembership | None, Person | None, JsonResponse | None]:
    user, err = _require_session_user(request)
    if err is not None:
        return None, None, None, None, err

    org = get_object_or_404(Org, id=org_id)
    membership = _get_membership(user, org)
    if membership is None:
        return user, org, None, None, _json_error("forbidden", status=403)

    person = get_object_or_404(Person, id=person_id, org=org)

    if membership.role in {OrgMembership.Role.ADMIN, OrgMembership.Role.PM}:
        return user, org, membership, person, None

    if person.user_id and str(person.user_id) == str(user.id):
        return user, org, membership, person, None

    return user, org, membership, person, _json_error("forbidden", status=403)


def _parse_weekday(value) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _parse_time_value(value, field: str) -> time | None:
    if value is None or str(value).strip() == "":
        return None
    if not isinstance(value, str):
        return None

    try:
        return time.fromisoformat(value.strip())
    except ValueError:
        return None


def _parse_datetime_value(value, field: str) -> datetime | None:
    if value is None or str(value).strip() == "":
        return None
    if not isinstance(value, str):
        return None

    dt = parse_datetime(value.strip())
    if dt is None:
        return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return None
    return dt


@require_http_methods(["GET"])
def person_availability_view(request: HttpRequest, org_id, person_id) -> JsonResponse:
    """Get a Person's availability schedule (weekly windows + exceptions).

    Auth: Session (ADMIN/PM for the org; or the Person themselves).
    Inputs:
      - Path `org_id`, `person_id`.
      - Optional query `start_at`, `end_at` (ISO datetimes, timezone-aware) for a computed summary.
    Returns: `{timezone, weekly_windows, exceptions, summary}`.
    """

    _user, _org, _membership, person, err = _require_person_schedule_access(
        request, org_id, person_id
    )
    if err is not None:
        return err
    assert person is not None

    weekly_windows = list(
        PersonAvailabilityWeeklyWindow.objects.filter(person=person).order_by(
            "weekday", "start_time", "created_at"
        )
    )
    exceptions = list(
        PersonAvailabilityException.objects.filter(person=person).order_by(
            "starts_at", "created_at"
        )
    )

    start_at = None
    end_at = None

    if request.GET.get("start_at") is not None:
        start_at = _parse_datetime_value(request.GET.get("start_at"), "start_at")
        if start_at is None:
            return _json_error("start_at must be an ISO datetime with timezone", status=400)

    if request.GET.get("end_at") is not None:
        end_at = _parse_datetime_value(request.GET.get("end_at"), "end_at")
        if end_at is None:
            return _json_error("end_at must be an ISO datetime with timezone", status=400)

    if start_at is None:
        start_at = timezone.now()
    if end_at is None:
        end_at = start_at + timedelta(days=14)

    summary = summarize_availability(
        tz_name=str(person.timezone or "UTC"),
        weekly_windows=[
            WeeklyWindow(weekday=w.weekday, start_time=w.start_time, end_time=w.end_time)
            for w in weekly_windows
        ],
        exceptions=[
            ExceptionWindow(kind=str(e.kind), starts_at=e.starts_at, ends_at=e.ends_at)
            for e in exceptions
        ],
        start_at=start_at,
        end_at=end_at,
    )

    return JsonResponse(
        {
            "timezone": str(person.timezone or "UTC"),
            "weekly_windows": [_weekly_window_dict(w) for w in weekly_windows],
            "exceptions": [_availability_exception_dict(e) for e in exceptions],
            "summary": summary,
        }
    )


@require_http_methods(["POST"])
def person_weekly_windows_create_view(request: HttpRequest, org_id, person_id) -> JsonResponse:
    """Create a weekly availability window for a Person."""

    user, org, _membership, person, err = _require_person_schedule_access(
        request, org_id, person_id
    )
    if err is not None:
        return err
    assert user is not None
    assert org is not None
    assert person is not None

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    weekday = _parse_weekday(payload.get("weekday"))
    if weekday is None or weekday < 0 or weekday > 6:
        return _json_error("weekday must be an integer between 0 and 6", status=400)

    start_time = _parse_time_value(payload.get("start_time"), "start_time")
    end_time = _parse_time_value(payload.get("end_time"), "end_time")
    if start_time is None:
        return _json_error("start_time must be HH:MM", status=400)
    if end_time is None:
        return _json_error("end_time must be HH:MM", status=400)
    if end_time <= start_time:
        return _json_error("end_time must be after start_time", status=400)

    try:
        window = PersonAvailabilityWeeklyWindow.objects.create(
            person=person,
            weekday=weekday,
            start_time=start_time,
            end_time=end_time,
        )
    except IntegrityError:
        return _json_error("weekly window already exists", status=400)

    write_audit_event(
        org=org,
        actor_user=user,
        event_type="person_availability.weekly_window.created",
        metadata={
            "person_id": str(person.id),
            "weekly_window_id": str(window.id),
            "weekday": int(window.weekday),
            "start_time": window.start_time.isoformat(timespec="minutes"),
            "end_time": window.end_time.isoformat(timespec="minutes"),
        },
    )

    return JsonResponse({"weekly_window": _weekly_window_dict(window)})


@require_http_methods(["PATCH", "DELETE"])
def person_weekly_window_detail_view(
    request: HttpRequest, org_id, person_id, weekly_window_id
) -> JsonResponse:
    """Update or delete a weekly availability window for a Person."""

    user, org, _membership, person, err = _require_person_schedule_access(
        request, org_id, person_id
    )
    if err is not None:
        return err
    assert user is not None
    assert org is not None
    assert person is not None

    window = get_object_or_404(
        PersonAvailabilityWeeklyWindow,
        id=weekly_window_id,
        person=person,
    )

    if request.method == "DELETE":
        window_id = str(window.id)
        window.delete()
        write_audit_event(
            org=org,
            actor_user=user,
            event_type="person_availability.weekly_window.deleted",
            metadata={"person_id": str(person.id), "weekly_window_id": window_id},
        )
        return JsonResponse({}, status=204)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    fields_changed: list[str] = []
    update_fields: set[str] = set()

    if "weekday" in payload:
        weekday = _parse_weekday(payload.get("weekday"))
        if weekday is None or weekday < 0 or weekday > 6:
            return _json_error("weekday must be an integer between 0 and 6", status=400)
        if weekday != int(window.weekday):
            window.weekday = weekday
            update_fields.add("weekday")
            fields_changed.append("weekday")

    if "start_time" in payload:
        start_time = _parse_time_value(payload.get("start_time"), "start_time")
        if start_time is None:
            return _json_error("start_time must be HH:MM", status=400)
        if start_time != window.start_time:
            window.start_time = start_time
            update_fields.add("start_time")
            fields_changed.append("start_time")

    if "end_time" in payload:
        end_time = _parse_time_value(payload.get("end_time"), "end_time")
        if end_time is None:
            return _json_error("end_time must be HH:MM", status=400)
        if end_time != window.end_time:
            window.end_time = end_time
            update_fields.add("end_time")
            fields_changed.append("end_time")

    if window.end_time <= window.start_time:
        return _json_error("end_time must be after start_time", status=400)

    if update_fields:
        window.save(update_fields=sorted(update_fields))
        write_audit_event(
            org=org,
            actor_user=user,
            event_type="person_availability.weekly_window.updated",
            metadata={
                "person_id": str(person.id),
                "weekly_window_id": str(window.id),
                "fields_changed": fields_changed,
            },
        )

    return JsonResponse({"weekly_window": _weekly_window_dict(window)})


@require_http_methods(["POST"])
def person_availability_exceptions_create_view(
    request: HttpRequest, org_id, person_id
) -> JsonResponse:
    """Create an availability exception (time off or extra availability) for a Person."""

    user, org, _membership, person, err = _require_person_schedule_access(
        request, org_id, person_id
    )
    if err is not None:
        return err
    assert user is not None
    assert org is not None
    assert person is not None

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    kind = str(payload.get("kind") or "").strip()
    if kind not in set(PersonAvailabilityException.Kind.values):
        return _json_error("kind must be one of: time_off, available", status=400)

    starts_at = _parse_datetime_value(payload.get("starts_at"), "starts_at")
    ends_at = _parse_datetime_value(payload.get("ends_at"), "ends_at")
    if starts_at is None:
        return _json_error("starts_at must be an ISO datetime with timezone", status=400)
    if ends_at is None:
        return _json_error("ends_at must be an ISO datetime with timezone", status=400)
    if ends_at <= starts_at:
        return _json_error("ends_at must be after starts_at", status=400)

    exc = PersonAvailabilityException.objects.create(
        person=person,
        kind=kind,
        starts_at=starts_at,
        ends_at=ends_at,
        title=str(payload.get("title") or "").strip(),
        notes=str(payload.get("notes") or "").strip(),
        created_by_user=user,
    )

    write_audit_event(
        org=org,
        actor_user=user,
        event_type="person_availability.exception.created",
        metadata={
            "person_id": str(person.id),
            "exception_id": str(exc.id),
            "kind": str(exc.kind),
        },
    )

    return JsonResponse({"exception": _availability_exception_dict(exc)})


@require_http_methods(["PATCH", "DELETE"])
def person_availability_exception_detail_view(
    request: HttpRequest, org_id, person_id, exception_id
) -> JsonResponse:
    """Update or delete an availability exception for a Person."""

    user, org, _membership, person, err = _require_person_schedule_access(
        request, org_id, person_id
    )
    if err is not None:
        return err
    assert user is not None
    assert org is not None
    assert person is not None

    exc = get_object_or_404(
        PersonAvailabilityException,
        id=exception_id,
        person=person,
    )

    if request.method == "DELETE":
        exc_id = str(exc.id)
        exc.delete()
        write_audit_event(
            org=org,
            actor_user=user,
            event_type="person_availability.exception.deleted",
            metadata={"person_id": str(person.id), "exception_id": exc_id},
        )
        return JsonResponse({}, status=204)

    try:
        payload = _parse_json(request)
    except ValueError as exc_parse:
        return _json_error(str(exc_parse), status=400)

    fields_changed: list[str] = []
    update_fields: set[str] = set()

    if "kind" in payload:
        kind = str(payload.get("kind") or "").strip()
        if kind not in set(PersonAvailabilityException.Kind.values):
            return _json_error("kind must be one of: time_off, available", status=400)
        if kind != str(exc.kind):
            exc.kind = kind
            update_fields.add("kind")
            fields_changed.append("kind")

    if "starts_at" in payload:
        starts_at = _parse_datetime_value(payload.get("starts_at"), "starts_at")
        if starts_at is None:
            return _json_error("starts_at must be an ISO datetime with timezone", status=400)
        if starts_at != exc.starts_at:
            exc.starts_at = starts_at
            update_fields.add("starts_at")
            fields_changed.append("starts_at")

    if "ends_at" in payload:
        ends_at = _parse_datetime_value(payload.get("ends_at"), "ends_at")
        if ends_at is None:
            return _json_error("ends_at must be an ISO datetime with timezone", status=400)
        if ends_at != exc.ends_at:
            exc.ends_at = ends_at
            update_fields.add("ends_at")
            fields_changed.append("ends_at")

    if "title" in payload:
        title = str(payload.get("title") or "").strip()
        if title != (exc.title or ""):
            exc.title = title
            update_fields.add("title")
            fields_changed.append("title")

    if "notes" in payload:
        notes = str(payload.get("notes") or "").strip()
        if notes != (exc.notes or ""):
            exc.notes = notes
            update_fields.add("notes")
            fields_changed.append("notes")

    if exc.ends_at <= exc.starts_at:
        return _json_error("ends_at must be after starts_at", status=400)

    if update_fields:
        exc.save(update_fields=sorted(update_fields))
        write_audit_event(
            org=org,
            actor_user=user,
            event_type="person_availability.exception.updated",
            metadata={
                "person_id": str(person.id),
                "exception_id": str(exc.id),
                "fields_changed": fields_changed,
            },
        )

    return JsonResponse({"exception": _availability_exception_dict(exc)})


@require_http_methods(["GET"])
def org_people_availability_search_view(request: HttpRequest, org_id) -> JsonResponse:
    """Search People availability within a time range (PM/admin; session-only).

    Auth: Session (ADMIN/PM) for the org.
    Inputs: Query `start_at`, `end_at` (ISO datetimes, timezone-aware).
    Returns: `{matches: [{person_id, has_availability, next_available_at, minutes_available}]}`.
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

    start_at = _parse_datetime_value(request.GET.get("start_at"), "start_at")
    end_at = _parse_datetime_value(request.GET.get("end_at"), "end_at")
    if start_at is None:
        return _json_error(
            "start_at is required and must be an ISO datetime with timezone", status=400
        )
    if end_at is None:
        return _json_error(
            "end_at is required and must be an ISO datetime with timezone", status=400
        )

    people = list(
        Person.objects.filter(org=org)
        .prefetch_related("availability_weekly_windows", "availability_exceptions")
        .order_by("full_name", "preferred_name", "created_at")
    )

    matches = []
    for person in people:
        weekly_windows = [
            WeeklyWindow(weekday=w.weekday, start_time=w.start_time, end_time=w.end_time)
            for w in person.availability_weekly_windows.all()
        ]
        exceptions = [
            ExceptionWindow(kind=str(e.kind), starts_at=e.starts_at, ends_at=e.ends_at)
            for e in person.availability_exceptions.all()
        ]
        summary = summarize_availability(
            tz_name=str(person.timezone or "UTC"),
            weekly_windows=weekly_windows,
            exceptions=exceptions,
            start_at=start_at,
            end_at=end_at,
        )
        matches.append({"person_id": str(person.id), **summary})

    return JsonResponse(
        {
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "matches": matches,
        }
    )
