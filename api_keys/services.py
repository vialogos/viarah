from __future__ import annotations

import secrets
from dataclasses import dataclass

from django.contrib.auth.hashers import check_password, make_password
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import ApiKey

_DUMMY_SECRET_HASH = make_password("invalid-api-key-secret")


@dataclass(frozen=True, slots=True)
class TokenParts:
    prefix: str
    secret: str


@dataclass(frozen=True, slots=True)
class MintedToken:
    token: str
    prefix: str
    secret: str


def parse_token(token: str) -> TokenParts | None:
    token = token.strip()
    if not token.startswith("vrak_"):
        return None

    rest = token.removeprefix("vrak_")
    if "." not in rest:
        return None

    prefix, secret = rest.split(".", 1)
    if not prefix or not secret:
        return None
    if "." in prefix:
        return None

    return TokenParts(prefix=prefix, secret=secret)


def mint_token(prefix: str, secret: str) -> MintedToken:
    return MintedToken(token=f"vrak_{prefix}.{secret}", prefix=prefix, secret=secret)


def generate_prefix() -> str:
    return secrets.token_hex(6)


def generate_secret() -> str:
    return secrets.token_urlsafe(32)


def create_api_key(
    *,
    org,
    name: str,
    scopes: list[str] | None = None,
    project_id=None,
    created_by_user=None,
) -> tuple[ApiKey, MintedToken]:
    cleaned_name = name.strip()
    if not cleaned_name:
        raise ValueError("name is required")

    normalized_scopes = normalize_scopes(scopes)

    for _ in range(10):
        prefix = generate_prefix()
        secret = generate_secret()
        token = mint_token(prefix, secret)

        try:
            with transaction.atomic():
                key = ApiKey.objects.create(
                    org=org,
                    project_id=project_id,
                    name=cleaned_name,
                    prefix=prefix,
                    secret_hash=make_password(secret),
                    scopes=normalized_scopes,
                    created_by_user=created_by_user,
                )
            return key, token
        except IntegrityError:
            continue

    raise RuntimeError("failed to mint unique api key prefix")


def rotate_api_key(*, api_key: ApiKey) -> MintedToken:
    if api_key.revoked_at is not None:
        raise ValueError("cannot rotate revoked key")

    secret = generate_secret()
    api_key.secret_hash = make_password(secret)
    api_key.rotated_at = timezone.now()
    api_key.save(update_fields=["secret_hash", "rotated_at", "updated_at"])
    return mint_token(api_key.prefix, secret)


def revoke_api_key(*, api_key: ApiKey) -> None:
    if api_key.revoked_at is not None:
        return

    api_key.revoked_at = timezone.now()
    api_key.save(update_fields=["revoked_at", "updated_at"])


def verify_token(*, prefix: str, secret: str) -> ApiKey | None:
    api_key = ApiKey.objects.filter(prefix=prefix).select_related("org").first()
    if api_key is None:
        check_password(secret, _DUMMY_SECRET_HASH)
        return None

    if api_key.revoked_at is not None:
        check_password(secret, api_key.secret_hash)
        return None

    if not check_password(secret, api_key.secret_hash):
        return None

    return api_key


def normalize_scopes(scopes: list[str] | None) -> list[str]:
    if scopes is None:
        return [ApiKey.Scope.READ]

    normalized: list[str] = []
    for scope in scopes:
        value = str(scope).strip().lower()
        if not value:
            continue
        if value not in ApiKey.Scope.values:
            raise ValueError("invalid scope")
        if value not in normalized:
            normalized.append(value)

    if not normalized:
        return [ApiKey.Scope.READ]

    return normalized

