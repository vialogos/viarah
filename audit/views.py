import hashlib

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from identity.models import Org, OrgMembership, Person
from identity.rbac import effective_org_role

from .models import AuditEvent


def _json_error(message: str, *, status: int) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def _person_avatar_url(*, person: Person | None, user_email: str | None) -> str | None:
    avatar_url = None

    if person is not None and getattr(person, "avatar_file", None):
        try:
            if person.avatar_file:
                avatar_url = person.avatar_file.url
        except ValueError:
            avatar_url = None

    if avatar_url is None:
        email = (person.email if person is not None else None) or (user_email or "")
        email = email.strip().lower()
        if email:
            h = hashlib.md5(email.encode("utf-8"), usedforsecurity=False).hexdigest()
            avatar_url = f"https://www.gravatar.com/avatar/{h}?d=identicon&s=128"

    return avatar_url


@login_required
@require_http_methods(["GET"])
def list_audit_events_view(request: HttpRequest, org_id) -> JsonResponse:
    """List recent audit events for an org (newest first).

    Auth: Session (ADMIN/PM) for the org (see `docs/api/scope-map.yaml` operation
    `audit__org_audit_events_get`).
    Inputs: Path `org_id`.
    Returns: `{events: [...]}` (up to 100 events) including event metadata.
    Side effects: None.
    """
    org = get_object_or_404(Org, id=org_id)
    role = effective_org_role(user=request.user, org=org)
    if role not in {
        OrgMembership.Role.ADMIN,
        OrgMembership.Role.PM,
    }:
        return _json_error("forbidden", status=403)

    events = list(
        AuditEvent.objects.filter(org=org)
        .select_related("actor_user")
        .order_by("-created_at")[:100]
    )

    actor_user_ids = [e.actor_user_id for e in events if e.actor_user_id]
    person_by_user_id: dict[str, Person] = {}
    if actor_user_ids:
        for person in (
            Person.objects.filter(org=org, user_id__in=actor_user_ids)
            .select_related("user")
            .only("id", "user_id", "email", "avatar_file")
        ):
            if person.user_id:
                person_by_user_id[str(person.user_id)] = person

    payload_events: list[dict] = []
    for e in events:
        actor_user_id = str(e.actor_user_id) if e.actor_user_id else None
        actor_user = (
            {
                "id": str(e.actor_user.id),
                "email": e.actor_user.email,
                "display_name": e.actor_user.display_name,
            }
            if e.actor_user_id and e.actor_user
            else None
        )
        actor_person = person_by_user_id.get(actor_user_id) if actor_user_id else None
        payload_events.append(
            {
                "id": str(e.id),
                "created_at": e.created_at.isoformat(),
                "event_type": e.event_type,
                "actor_user_id": actor_user_id,
                "actor_user": actor_user,
                "actor_person_id": str(actor_person.id) if actor_person else None,
                "actor_avatar_url": _person_avatar_url(
                    person=actor_person, user_email=(actor_user["email"] if actor_user else None)
                ),
                "metadata": e.metadata,
            }
        )
    return JsonResponse({"events": payload_events})
