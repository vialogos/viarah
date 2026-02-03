from __future__ import annotations

from dataclasses import dataclass

from django.http import HttpRequest, JsonResponse

from .services import parse_token, verify_token


@dataclass(frozen=True, slots=True)
class ApiKeyPrincipal:
    api_key_id: str
    org_id: str
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
            project_id=str(api_key.project_id) if api_key.project_id else None,
            scopes=list(api_key.scopes or []),
        )
        request.api_key = api_key

        return self.get_response(request)
