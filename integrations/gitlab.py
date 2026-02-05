from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .services import gitlab_project_path_for_api


@dataclass(frozen=True, slots=True)
class GitLabHttpError(Exception):
    status_code: int
    body: str
    headers: dict[str, str]


class GitLabClient:
    """
    Minimal GitLab REST client for fetching Issue/MR metadata.

    Intentionally uses stdlib urllib to avoid adding a heavy dependency.
    """

    def __init__(self, *, base_url: str, token: str, timeout_seconds: int = 10) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout_seconds = timeout_seconds

    def get_issue(self, *, project_path: str, issue_iid: int) -> dict[str, Any]:
        encoded = gitlab_project_path_for_api(project_path)
        url = f"{self._base_url}/api/v4/projects/{encoded}/issues/{issue_iid}"
        return self._request_json(url)

    def get_merge_request(self, *, project_path: str, merge_request_iid: int) -> dict[str, Any]:
        encoded = gitlab_project_path_for_api(project_path)
        url = f"{self._base_url}/api/v4/projects/{encoded}/merge_requests/{merge_request_iid}"
        return self._request_json(url)

    def get_user(self) -> dict[str, Any]:
        """Fetch the current user to validate the provided token."""
        url = f"{self._base_url}/api/v4/user"
        return self._request_json(url)

    def _request_json(self, url: str) -> dict[str, Any]:
        request = Request(
            url,
            headers={
                "PRIVATE-TOKEN": self._token,
                "Accept": "application/json",
                "User-Agent": "ViaRah/1.0",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = response.read().decode("utf-8")
                return json.loads(payload or "{}")
        except HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8")
            except Exception:
                body = ""
            headers = {k: v for (k, v) in (exc.headers.items() if exc.headers else [])}
            raise GitLabHttpError(status_code=int(exc.code), body=body, headers=headers) from exc
        except URLError as exc:
            raise GitLabHttpError(status_code=0, body=str(exc), headers={}) from exc
