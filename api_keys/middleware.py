from __future__ import annotations

from dataclasses import dataclass

from django.http import HttpRequest, JsonResponse
from django.utils import timezone

from .models import ApiKey
from .services import parse_token, verify_token


@dataclass(frozen=True, slots=True)
class ApiKeyPrincipal:
    api_key_id: str
    org_id: str
    owner_user_id: str
    project_id: str | None
    scopes: list[str]


class ApiKeyAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        request.api_key_principal = None

        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header:
            return self.get_response(request)

        parts = auth_header.split(None, 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return self.get_response(request)

        raw_token = parts[1].strip()
        token_parts = parse_token(raw_token)
        if token_parts is None:
            return JsonResponse({"error": "unauthorized"}, status=401)

        api_key = verify_token(prefix=token_parts.prefix, secret=token_parts.secret)
        if api_key is None:
            return JsonResponse({"error": "unauthorized"}, status=401)

        request.api_key_principal = ApiKeyPrincipal(
            api_key_id=str(api_key.id),
            org_id=str(api_key.org_id),
            owner_user_id=str(api_key.owner_user_id),
            project_id=str(api_key.project_id) if api_key.project_id else None,
            scopes=list(api_key.scopes or []),
        )
        request.api_key = api_key

        now = timezone.now()
        if api_key.last_used_at is None or (now - api_key.last_used_at).total_seconds() > 300:
            ApiKey.objects.filter(id=api_key.id).update(last_used_at=now)

        return self.get_response(request)


class ApiKeyCsrfBypassMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header:
            parts = auth_header.split(None, 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                raw_token = parts[1].strip()
                if parse_token(raw_token) is not None:
                    request._dont_enforce_csrf_checks = True  # noqa: SLF001

        return self.get_response(request)
