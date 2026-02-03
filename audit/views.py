from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from identity.models import Org, OrgMembership

from .models import AuditEvent


def _json_error(message: str, *, status: int) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


@login_required
@require_http_methods(["GET"])
def list_audit_events_view(request: HttpRequest, org_id) -> JsonResponse:
    org = get_object_or_404(Org, id=org_id)
    membership = OrgMembership.objects.filter(user=request.user, org=org).first()
    if membership is None or membership.role not in {
        OrgMembership.Role.ADMIN,
        OrgMembership.Role.PM,
    }:
        return _json_error("forbidden", status=403)

    events = (
        AuditEvent.objects.filter(org=org)
        .select_related("actor_user")
        .order_by("-created_at")[:100]
    )
    return JsonResponse(
        {
            "events": [
                {
                    "id": str(e.id),
                    "created_at": e.created_at.isoformat(),
                    "event_type": e.event_type,
                    "actor_user_id": str(e.actor_user_id) if e.actor_user_id else None,
                    "metadata": e.metadata,
                }
                for e in events
            ]
        }
    )
