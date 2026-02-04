from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_http_methods

from .services import (
    build_public_share_link_html,
    record_share_link_access,
    resolve_active_share_link,
)


@require_http_methods(["GET"])
def public_share_link_view(request: HttpRequest, token: str) -> HttpResponse:
    share_link = resolve_active_share_link(token=token)
    if share_link is None:
        return HttpResponse("not found", status=404, content_type="text/plain")

    record_share_link_access(
        share_link=share_link,
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT"),
    )

    html = build_public_share_link_html(share_link=share_link)
    return HttpResponse(html, content_type="text/html")

