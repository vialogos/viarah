from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model

from .models import Org, OrgMembership


def platform_org_role(user) -> str | None:
    """Return the implicit org role for platform users (issue #55).

    Platform role semantics:
    - `is_superuser` => platform-admin (treat as org `admin` across the instance).
    - `is_staff` => platform-pm (treat as org `pm` across the instance).
    """
    if not getattr(user, "is_authenticated", False):
        return None
    if getattr(user, "is_superuser", False):
        return OrgMembership.Role.ADMIN
    if getattr(user, "is_staff", False):
        return OrgMembership.Role.PM
    return None


def platform_role_key(user) -> str:
    """Return `admin|pm|none` for session UI consumers."""
    role = platform_org_role(user)
    if role == OrgMembership.Role.ADMIN:
        return "admin"
    if role == OrgMembership.Role.PM:
        return "pm"
    return "none"


def effective_org_role(*, user, org: Org) -> str | None:
    role = platform_org_role(user)
    if role is not None:
        return role

    membership = OrgMembership.objects.filter(user=user, org=org).only("role").first()
    return membership.role if membership is not None else None


def effective_role_and_membership(*, user, org: Org) -> tuple[str | None, OrgMembership | None]:
    """Return the effective role (platform role or membership role) and the membership row.

    Platform users receive `(role, None)` because they may not have an `OrgMembership` row.
    """
    role = platform_org_role(user)
    if role is not None:
        return role, None

    membership = OrgMembership.objects.filter(user=user, org=org).select_related("org").first()
    if membership is None:
        return None, None
    return membership.role, membership


def effective_role_for_org_id(*, user, org_id) -> str | None:
    role = platform_org_role(user)
    if role is not None:
        return role
    membership = OrgMembership.objects.filter(user=user, org_id=org_id).only("role").first()
    return membership.role if membership is not None else None


def user_id_has_platform_role(*, user_id: uuid.UUID) -> bool:
    user_model = get_user_model()
    user = user_model.objects.filter(id=user_id).only("is_staff", "is_superuser").first()
    if user is None:
        return False
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_staff", False))
