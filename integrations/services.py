from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

from cryptography.fernet import Fernet, InvalidToken


class IntegrationConfigError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ParsedGitLabUrl:
    origin: str
    project_path: str
    gitlab_type: str
    gitlab_iid: int
    canonical_web_url: str


def normalize_origin(base_url: str) -> str:
    """
    Normalize an origin-like URL (scheme + host [+ port]) into `https://host[:port]`.

    This keeps storage consistent and enables strict origin matching when users attach links.
    """

    raw = str(base_url or "").strip()
    if not raw:
        raise ValueError("base_url is required")

    split = urlsplit(raw)
    if split.scheme not in {"http", "https"}:
        raise ValueError("base_url must use http or https")
    if split.username or split.password:
        raise ValueError("base_url must not include credentials")
    if not split.hostname:
        raise ValueError("base_url must include a host")
    if split.path not in {"", "/"} or split.query or split.fragment:
        raise ValueError("base_url must be an origin (no path/query/fragment)")

    host = split.hostname
    port = split.port
    netloc = f"{host}:{port}" if port else host
    return f"{split.scheme}://{netloc}"


def parse_gitlab_web_url(url: str) -> ParsedGitLabUrl:
    """
    Parse a canonical GitLab Issue/MR URL and extract project path + iid.

    Supported forms:
    - https://gitlab.example.com/group/project/-/issues/123
    - https://gitlab.example.com/group/project/-/merge_requests/7
    """

    raw = str(url or "").strip()
    if not raw:
        raise ValueError("url is required")

    split = urlsplit(raw)
    if split.scheme not in {"http", "https"}:
        raise ValueError("url must include http or https scheme")
    if split.username or split.password:
        raise ValueError("url must not include credentials")
    if not split.hostname:
        raise ValueError("url must include a host")

    host = split.hostname
    port = split.port
    netloc = f"{host}:{port}" if port else host
    origin = f"{split.scheme}://{netloc}"

    parts = [p for p in split.path.split("/") if p]
    try:
        dash_index = parts.index("-")
    except ValueError as exc:
        raise ValueError("url must contain /-/<type>/<iid>") from exc

    if dash_index + 2 >= len(parts):
        raise ValueError("url must contain /-/<type>/<iid>")

    project_parts = parts[:dash_index]
    type_part = parts[dash_index + 1]
    iid_part = parts[dash_index + 2]

    if not project_parts:
        raise ValueError("url missing project path")

    if type_part == "issues":
        gitlab_type = "issue"
        type_segment = "issues"
    elif type_part == "merge_requests":
        gitlab_type = "mr"
        type_segment = "merge_requests"
    else:
        raise ValueError("url must be a GitLab issue or merge request link")

    try:
        gitlab_iid = int(iid_part)
    except ValueError as exc:
        raise ValueError("url iid must be an integer") from exc
    if gitlab_iid <= 0:
        raise ValueError("url iid must be a positive integer")

    project_path = "/".join(project_parts)
    canonical_web_url = f"{origin}/{project_path}/-/{type_segment}/{gitlab_iid}"

    return ParsedGitLabUrl(
        origin=origin,
        project_path=project_path,
        gitlab_type=gitlab_type,
        gitlab_iid=gitlab_iid,
        canonical_web_url=canonical_web_url,
    )


def gitlab_project_path_for_api(project_path: str) -> str:
    return quote(project_path, safe="")


def hash_webhook_secret(secret: str) -> str:
    raw = str(secret or "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def webhook_secret_matches(*, expected_hash: str, provided_secret: str) -> bool:
    provided_hash = hash_webhook_secret(provided_secret)
    return hmac.compare_digest(str(expected_hash or ""), provided_hash)


def _require_encryption_key() -> bytes:
    raw = os.environ.get("VIA_RAH_ENCRYPTION_KEY", "").strip()
    if not raw:
        raise IntegrationConfigError("VIA_RAH_ENCRYPTION_KEY is required")
    return raw.encode("utf-8")


def encrypt_token(token: str) -> str:
    key = _require_encryption_key()
    fernet = Fernet(key)
    return fernet.encrypt(str(token).encode("utf-8")).decode("utf-8")


def decrypt_token(token_ciphertext: str) -> str:
    key = _require_encryption_key()
    fernet = Fernet(key)
    try:
        return fernet.decrypt(str(token_ciphertext).encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise IntegrationConfigError("invalid token ciphertext") from exc
