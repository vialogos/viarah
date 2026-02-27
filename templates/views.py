from __future__ import annotations

import json

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from audit.services import write_audit_event
from identity.models import Org, OrgMembership
from identity.rbac import platform_org_role

from .models import Template, TemplateVersion
from .services import TemplateValidationError, create_template, create_template_version


def _json_error(message: str, *, status: int) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def _parse_json(request: HttpRequest) -> dict:
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise ValueError("invalid JSON") from None

    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")

    return payload


def _require_authenticated_user(request: HttpRequest):
    if not request.user.is_authenticated:
        return None
    return request.user


def _get_api_key_principal(request: HttpRequest):
    return getattr(request, "api_key_principal", None)


def _principal_has_scope(principal, required: str) -> bool:
    scopes = set(getattr(principal, "scopes", None) or [])
    if required == "read":
        return "read" in scopes or "write" in scopes
    return required in scopes


def _require_org(org_id) -> Org | None:
    return Org.objects.filter(id=org_id).first()


def _require_org_access(
    request: HttpRequest,
    org_id,
    *,
    required_scope: str,
    allowed_roles: set[str],
) -> tuple[Org | None, OrgMembership | None, object | None, JsonResponse | None]:
    org = _require_org(org_id)
    if org is None:
        return None, None, None, _json_error("not found", status=404)

    principal = _get_api_key_principal(request)
    if principal is not None:
        if str(org.id) != str(principal.org_id):
            return org, None, principal, _json_error("forbidden", status=403)
        if not _principal_has_scope(principal, required_scope):
            return org, None, principal, _json_error("forbidden", status=403)
        return org, None, principal, None

    user = _require_authenticated_user(request)
    if user is None:
        return org, None, None, _json_error("unauthorized", status=401)

    platform_role = platform_org_role(user)
    if platform_role is not None and platform_role in allowed_roles:
        return org, OrgMembership(org=org, user=user, role=platform_role), None, None

    membership = (
        OrgMembership.objects.filter(user=user, org=org, role__in=allowed_roles)
        .select_related("org")
        .first()
    )
    if membership is None:
        return org, None, None, _json_error("forbidden", status=403)

    return org, membership, None, None


def _template_dict(template: Template) -> dict:
    return {
        "id": str(template.id),
        "org_id": str(template.org_id),
        "type": template.type,
        "name": template.name,
        "description": template.description,
        "current_version_id": (
            str(template.current_version_id) if template.current_version_id else None
        ),
        "created_at": template.created_at.isoformat(),
        "updated_at": template.updated_at.isoformat(),
    }


def _template_version_dict(version: TemplateVersion, *, include_body: bool = False) -> dict:
    payload = {
        "id": str(version.id),
        "template_id": str(version.template_id),
        "version": int(version.version),
        "created_by_user_id": (
            str(version.created_by_user_id) if version.created_by_user_id else None
        ),
        "created_at": version.created_at.isoformat(),
    }
    if include_body:
        payload["body"] = version.body
    return payload


@require_http_methods(["GET", "POST"])
def templates_collection_view(request: HttpRequest, org_id) -> JsonResponse:
    """List or create templates for an org.

    Auth: Session or API key (see `docs/api/scope-map.yaml` operations
    `templates__templates_get` and `templates__templates_post`).
    Inputs: Path `org_id`; optional query `type`; POST JSON `{type, name, description?, body}`.
    Returns: `{templates: [...]}` for GET; `{template}` for POST.
    Side effects: POST creates a template + initial version and writes an audit event.
    """
    required_scope = "read" if request.method == "GET" else "write"
    roles = {OrgMembership.Role.ADMIN, OrgMembership.Role.PM, OrgMembership.Role.MEMBER}
    if request.method != "GET":
        roles = {OrgMembership.Role.ADMIN, OrgMembership.Role.PM}

    org, membership, _principal, err = _require_org_access(
        request, org_id, required_scope=required_scope, allowed_roles=roles
    )
    if err is not None:
        return err

    if request.method == "GET":
        qs = Template.objects.filter(org=org).order_by("-updated_at", "-created_at")
        template_type = request.GET.get("type")
        if template_type is not None and str(template_type).strip():
            qs = qs.filter(type=str(template_type).strip())
        return JsonResponse({"templates": [_template_dict(t) for t in qs]})

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    try:
        template, version = create_template(
            org=org,
            template_type=payload.get("type"),
            name=payload.get("name"),
            description=payload.get("description"),
            body=payload.get("body"),
            created_by_user=request.user if membership is not None else None,
        )
    except TemplateValidationError as exc:
        return _json_error(exc.message, status=400)

    write_audit_event(
        org=org,
        actor_user=request.user if membership is not None else None,
        event_type="template.created",
        metadata={
            "template_id": str(template.id),
            "template_version_id": str(version.id),
            "template_type": template.type,
        },
    )

    return JsonResponse({"template": _template_dict(template)})


@require_http_methods(["GET"])
def template_detail_view(request: HttpRequest, org_id, template_id) -> JsonResponse:
    """Fetch a template with its versions.

    Auth: Session or API key (read) (see `docs/api/scope-map.yaml` operation
    `templates__template_get`).
    Inputs: Path `org_id`, `template_id`.
    Returns: `{template, current_version_body, versions}`.
    Side effects: None.
    """
    org, _membership, _principal, err = _require_org_access(
        request,
        org_id,
        required_scope="read",
        allowed_roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM, OrgMembership.Role.MEMBER},
    )
    if err is not None:
        return err

    template = (
        Template.objects.filter(id=template_id, org=org).select_related("current_version").first()
    )
    if template is None:
        return _json_error("not found", status=404)

    versions = list(
        TemplateVersion.objects.filter(template=template).order_by("-version", "-created_at")
    )
    return JsonResponse(
        {
            "template": _template_dict(template),
            "current_version_body": (
                template.current_version.body if template.current_version_id else None
            ),
            "versions": [_template_version_dict(v) for v in versions],
        }
    )


@require_http_methods(["POST"])
def template_versions_collection_view(request: HttpRequest, org_id, template_id) -> JsonResponse:
    """Create a new template version.

    Auth: Session or API key (write) (see `docs/api/scope-map.yaml` operation
    `templates__template_versions_post`).
    Inputs: Path `org_id`, `template_id`; POST JSON `{body}`.
    Returns: `{template, version}`.
    Side effects: Creates a `TemplateVersion`, updates the template's current version, and writes an
    audit event.
    """
    org, membership, _principal, err = _require_org_access(
        request,
        org_id,
        required_scope="write",
        allowed_roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM},
    )
    if err is not None:
        return err

    template = Template.objects.filter(id=template_id, org=org).first()
    if template is None:
        return _json_error("not found", status=404)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    try:
        version = create_template_version(
            template=template,
            body=payload.get("body"),
            created_by_user=request.user if membership is not None else None,
        )
    except TemplateValidationError as exc:
        return _json_error(exc.message, status=400)

    template.refresh_from_db(fields=["current_version_id", "updated_at"])

    write_audit_event(
        org=org,
        actor_user=request.user if membership is not None else None,
        event_type="template.version_created",
        metadata={
            "template_id": str(template.id),
            "template_version_id": str(version.id),
            "version": int(version.version),
        },
    )

    return JsonResponse(
        {"template": _template_dict(template), "version": _template_version_dict(version)}
    )


@require_http_methods(["GET"])
def template_version_detail_view(
    request: HttpRequest, org_id, template_id, version_id
) -> JsonResponse:
    """Fetch a specific template version (including body).

    Auth: Session or API key (read) (see `docs/api/scope-map.yaml` operation
    `templates__template_version_get`).
    Inputs: Path `org_id`, `template_id`, `version_id`.
    Returns: `{version}` (includes `body`).
    Side effects: None.
    """
    org, _membership, _principal, err = _require_org_access(
        request,
        org_id,
        required_scope="read",
        allowed_roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM, OrgMembership.Role.MEMBER},
    )
    if err is not None:
        return err

    template = Template.objects.filter(id=template_id, org=org).first()
    if template is None:
        return _json_error("not found", status=404)

    version = TemplateVersion.objects.filter(id=version_id, template=template).first()
    if version is None:
        return _json_error("not found", status=404)

    return JsonResponse({"version": _template_version_dict(version, include_body=True)})
