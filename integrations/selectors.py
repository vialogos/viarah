from __future__ import annotations

from typing import Literal

from .models import GlobalGitLabIntegration, OrgGitLabIntegration


def get_global_gitlab_integration() -> GlobalGitLabIntegration:
    row, _ = GlobalGitLabIntegration.objects.get_or_create(key="default")
    return row


def get_effective_gitlab_integration_for_org(
    *, org_id
) -> tuple[OrgGitLabIntegration | GlobalGitLabIntegration | None, Literal["org", "global", "none"]]:
    org_row = OrgGitLabIntegration.objects.filter(org_id=org_id).first()
    if org_row is not None:
        return org_row, "org"

    global_row = get_global_gitlab_integration()
    if str(global_row.base_url or "").strip():
        return global_row, "global"

    return None, "none"
