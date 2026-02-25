from __future__ import annotations

import json
import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from identity.models import Org, OrgMembership
from templates.models import Template, TemplateType, TemplateVersion
from work_items.models import Project, ProjectMembership

from .models import SoW, SoWPdfArtifact, SoWSigner, SoWVersion
from .services import SoWValidationError, create_sow, create_sow_version, send_sow, signer_respond
from .tasks import render_sow_version_pdf


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


def _require_session_user(request: HttpRequest):
    principal = getattr(request, "api_key_principal", None)
    if principal is not None:
        return None, _json_error("forbidden", status=403)
    if not request.user.is_authenticated:
        return None, _json_error("unauthorized", status=401)
    return request.user, None


def _require_org(org_id) -> Org | None:
    return Org.objects.filter(id=org_id).first()


def _require_membership(user, org: Org) -> OrgMembership | None:
    return OrgMembership.objects.filter(user=user, org=org).select_related("org").first()


def _require_pm_or_admin_membership(user, org: Org) -> OrgMembership | None:
    return (
        OrgMembership.objects.filter(
            user=user,
            org=org,
            role__in={OrgMembership.Role.ADMIN, OrgMembership.Role.PM},
        )
        .select_related("org")
        .first()
    )


def _sow_dict(sow: SoW) -> dict:
    return {
        "id": str(sow.id),
        "org_id": str(sow.org_id),
        "project_id": str(sow.project_id),
        "template_id": str(sow.template_id),
        "current_version_id": str(sow.current_version_id) if sow.current_version_id else None,
        "created_by_user_id": str(sow.created_by_user_id) if sow.created_by_user_id else None,
        "created_at": sow.created_at.isoformat(),
        "updated_at": sow.updated_at.isoformat(),
    }


def _version_dict(version: SoWVersion, *, include_body: bool = False) -> dict:
    payload = {
        "id": str(version.id),
        "sow_id": str(version.sow_id),
        "version": int(version.version),
        "template_version_id": str(version.template_version_id),
        "variables": version.variables_json or {},
        "status": version.status,
        "locked_at": version.locked_at.isoformat() if version.locked_at else None,
        "content_sha256": str(version.content_sha256 or "").strip() or None,
        "created_by_user_id": (
            str(version.created_by_user_id) if version.created_by_user_id else None
        ),
        "created_at": version.created_at.isoformat(),
    }
    if include_body:
        payload["body_markdown"] = version.body_markdown
        payload["body_html"] = version.body_html
    return payload


def _signer_dict(signer: SoWSigner) -> dict:
    return {
        "id": str(signer.id),
        "sow_version_id": str(signer.sow_version_id),
        "signer_user_id": str(signer.signer_user_id),
        "status": signer.status,
        "decision_comment": signer.decision_comment,
        "typed_signature": signer.typed_signature
        if signer.status == SoWSigner.Status.APPROVED
        else "",
        "responded_at": signer.responded_at.isoformat() if signer.responded_at else None,
        "created_at": signer.created_at.isoformat(),
    }


def _signer_dict_for_viewer(
    signer: SoWSigner,
    *,
    viewer_user_id: uuid.UUID,
    redact_for_client: bool,
) -> dict:
    payload = _signer_dict(signer)
    if redact_for_client and str(signer.signer_user_id) != str(viewer_user_id):
        payload["decision_comment"] = ""
        payload["typed_signature"] = ""
    return payload


def _version_summary_dict(version: SoWVersion) -> dict:
    return {
        "id": str(version.id),
        "version": int(version.version),
        "status": version.status,
        "locked_at": version.locked_at.isoformat() if version.locked_at else None,
        "created_at": version.created_at.isoformat(),
    }


def _pdf_artifact_dict(artifact: SoWPdfArtifact) -> dict:
    return {
        "id": str(artifact.id),
        "sow_version_id": str(artifact.sow_version_id),
        "status": artifact.status,
        "celery_task_id": artifact.celery_task_id or None,
        "created_at": artifact.created_at.isoformat(),
        "started_at": artifact.started_at.isoformat() if artifact.started_at else None,
        "completed_at": artifact.completed_at.isoformat() if artifact.completed_at else None,
        "blocked_urls": list(artifact.blocked_urls or []),
        "missing_images": list(artifact.missing_images or []),
        "error_code": artifact.error_code or None,
        "error_message": artifact.error_message or None,
        "qa_report": artifact.qa_report or {},
        "pdf_sha256": artifact.pdf_sha256 or None,
        "pdf_size_bytes": int(artifact.pdf_size_bytes or 0),
        "pdf_rendered_at": artifact.pdf_rendered_at.isoformat()
        if artifact.pdf_rendered_at
        else None,
    }


def _require_sow_read_access(*, user, org: Org, sow: SoW) -> JsonResponse | None:
    membership = _require_membership(user, org)
    if membership is None:
        return _json_error("forbidden", status=403)

    if membership.role in {OrgMembership.Role.ADMIN, OrgMembership.Role.PM}:
        return None

    if membership.role != OrgMembership.Role.CLIENT:
        return _json_error("forbidden", status=403)

    if not ProjectMembership.objects.filter(
        project_id=sow.project_id,
        user_id=membership.user_id,
    ).exists():
        return _json_error("not found", status=404)

    if sow.current_version_id is None:
        return _json_error("forbidden", status=403)

    signer = SoWSigner.objects.filter(
        sow_version_id=sow.current_version_id, signer_user_id=user.id
    ).first()
    if signer is None:
        return _json_error("forbidden", status=403)

    return None


@require_http_methods(["GET", "POST"])
def sows_collection_view(request: HttpRequest, org_id) -> JsonResponse:
    """List or create statements of work (SoWs).

    Auth: Session-only (see `docs/api/scope-map.yaml` operations `sows__sows_get` and
    `sows__sows_post`).
      - GET: ADMIN/PM can list all org SoWs; CLIENT can list SoWs where they are a signer.
      - POST: ADMIN/PM only.
    Inputs:
      - GET: Path `org_id`; optional query `project_id`, `status`.
      - POST: Path `org_id`; JSON fields: project_id, template_id, template_version_id?,
        variables, signer_user_ids.
    Returns:
      - GET: `{sows: [...]}` (list-friendly shape; version body omitted).
      - POST: `{sow, version, signers}` (version includes rendered body).
    Side effects:
      - GET: None.
      - POST: Creates `SoW`, `SoWVersion`, and signer rows.
    """
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    if request.method == "GET":
        membership = _require_membership(user, org)
        if membership is None:
            return _json_error("forbidden", status=403)

        sow_qs = SoW.objects.filter(org=org).exclude(current_version_id=None)
        if membership.role in {OrgMembership.Role.ADMIN, OrgMembership.Role.PM}:
            pass
        elif membership.role == OrgMembership.Role.CLIENT:
            sow_qs = sow_qs.filter(current_version__signers__signer_user_id=user.id)
            sow_qs = sow_qs.filter(project__memberships__user_id=user.id)
        else:
            return _json_error("forbidden", status=403)

        project_id_raw = request.GET.get("project_id")
        if project_id_raw is not None and str(project_id_raw).strip():
            try:
                project_id = uuid.UUID(str(project_id_raw))
            except (TypeError, ValueError):
                return _json_error("project_id must be a UUID", status=400)
            sow_qs = sow_qs.filter(project_id=project_id)

        status_raw = request.GET.get("status")
        if status_raw is not None and str(status_raw).strip():
            status = str(status_raw).strip()
            if status not in set(SoWVersion.Status.values):
                return _json_error("status must be a valid SoW status", status=400)
            sow_qs = sow_qs.filter(current_version__status=status)

        sows = list(
            sow_qs.select_related("current_version").order_by("-updated_at", "-created_at").all()
        )
        version_ids = [s.current_version_id for s in sows if s.current_version_id]

        signers_by_version_id: dict[uuid.UUID, list[SoWSigner]] = {}
        for signer in (
            SoWSigner.objects.filter(sow_version_id__in=version_ids)
            .order_by("created_at", "id")
            .all()
        ):
            signers_by_version_id.setdefault(signer.sow_version_id, []).append(signer)

        artifacts_by_version_id = {
            artifact.sow_version_id: artifact
            for artifact in SoWPdfArtifact.objects.filter(sow_version_id__in=version_ids).all()
        }

        redact_for_client = membership.role == OrgMembership.Role.CLIENT
        items: list[dict] = []
        for sow in sows:
            if sow.current_version is None:
                continue

            items.append(
                {
                    "sow": _sow_dict(sow),
                    "version": _version_summary_dict(sow.current_version),
                    "signers": [
                        _signer_dict_for_viewer(
                            signer, viewer_user_id=user.id, redact_for_client=redact_for_client
                        )
                        for signer in signers_by_version_id.get(sow.current_version_id, [])
                    ],
                    "pdf": (
                        _pdf_artifact_dict(artifacts_by_version_id[sow.current_version_id])
                        if sow.current_version_id in artifacts_by_version_id
                        else None
                    ),
                }
            )

        return JsonResponse({"sows": items})

    membership = _require_pm_or_admin_membership(user, org)
    if membership is None:
        return _json_error("forbidden", status=403)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    project_id_raw = payload.get("project_id")
    template_id_raw = payload.get("template_id")
    template_version_id_raw = payload.get("template_version_id")
    variables_raw = payload.get("variables") or {}
    signer_user_ids_raw = payload.get("signer_user_ids")

    if not isinstance(variables_raw, dict):
        return _json_error("variables must be an object", status=400)

    try:
        project_id = uuid.UUID(str(project_id_raw))
    except (TypeError, ValueError):
        return _json_error("project_id must be a UUID", status=400)

    try:
        template_id = uuid.UUID(str(template_id_raw))
    except (TypeError, ValueError):
        return _json_error("template_id must be a UUID", status=400)

    template = Template.objects.filter(id=template_id, org=org).first()
    if template is None:
        return _json_error("not found", status=404)
    if template.type != TemplateType.SOW:
        return _json_error("template must be a sow template", status=400)

    template_version = None
    if template_version_id_raw is not None and str(template_version_id_raw).strip():
        try:
            template_version_id = uuid.UUID(str(template_version_id_raw))
        except (TypeError, ValueError):
            return _json_error("template_version_id must be a UUID", status=400)
        template_version = TemplateVersion.objects.filter(
            id=template_version_id, template=template
        ).first()
        if template_version is None:
            return _json_error("invalid template_version_id", status=400)
    else:
        template_version = (
            TemplateVersion.objects.filter(
                id=template.current_version_id, template=template
            ).first()
            if template.current_version_id
            else None
        )
        if template_version is None:
            return _json_error("template has no current version", status=400)

    project = Project.objects.filter(id=project_id, org=org).first()
    if project is None:
        return _json_error("not found", status=404)

    if not isinstance(signer_user_ids_raw, list):
        return _json_error("signer_user_ids must be a list", status=400)

    signer_user_ids: list[uuid.UUID] = []
    for raw in signer_user_ids_raw:
        try:
            signer_user_ids.append(uuid.UUID(str(raw)))
        except (TypeError, ValueError):
            return _json_error("signer_user_ids must contain UUIDs", status=400)
    signer_user_ids = list(dict.fromkeys(signer_user_ids))
    if not signer_user_ids:
        return _json_error("signer_user_ids is required", status=400)

    User = get_user_model()
    signer_users = list(User.objects.filter(id__in=signer_user_ids).order_by("created_at"))
    if len(signer_users) != len(signer_user_ids):
        return _json_error("one or more signer_user_ids are invalid", status=400)

    valid_signer_ids = set(
        OrgMembership.objects.filter(
            org=org,
            role=OrgMembership.Role.CLIENT,
            user_id__in=signer_user_ids,
        ).values_list("user_id", flat=True)
    )
    if len(valid_signer_ids) != len(signer_user_ids):
        return _json_error("all signers must be client org members", status=400)

    try:
        sow, version = create_sow(
            org=org,
            project=project,
            template=template,
            template_version=template_version,
            variables=variables_raw,
            signer_users=signer_users,
            created_by_user=user if membership is not None else None,
        )
    except SoWValidationError as exc:
        return _json_error(exc.message, status=400)

    signers = list(SoWSigner.objects.filter(sow_version=version).order_by("created_at", "id").all())
    return JsonResponse(
        {
            "sow": _sow_dict(sow),
            "version": _version_dict(version, include_body=True),
            "signers": [_signer_dict(s) for s in signers],
        }
    )


@require_http_methods(["POST"])
def sow_versions_collection_view(request: HttpRequest, org_id, sow_id) -> JsonResponse:
    """Create a new SoW version (optionally changing variables/template/signers).

    Auth: Session-only (ADMIN/PM) (see `docs/api/scope-map.yaml` operation
    `sows__sow_versions_post`).
    Inputs: Path `org_id`, `sow_id`; JSON `{template_version_id?, variables?, signer_user_ids?}`.
    Returns: `{sow, version, signers}` (version includes rendered body).
    Side effects: Creates a new `SoWVersion`, updates the SoW current version, and resets signers.
    """
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_pm_or_admin_membership(user, org)
    if membership is None:
        return _json_error("forbidden", status=403)

    sow = SoW.objects.filter(id=sow_id, org=org).select_related("project", "template").first()
    if sow is None:
        return _json_error("not found", status=404)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    variables_raw = payload.get("variables")
    if variables_raw is None:
        prior_version = (
            SoWVersion.objects.filter(id=sow.current_version_id, sow=sow).first()
            if sow.current_version_id
            else None
        )
        variables_raw = prior_version.variables_json if prior_version else {}
    if not isinstance(variables_raw, dict):
        return _json_error("variables must be an object", status=400)

    signer_user_ids_raw = payload.get("signer_user_ids")
    if signer_user_ids_raw is None:
        if sow.current_version_id:
            signer_user_ids_raw = list(
                SoWSigner.objects.filter(sow_version_id=sow.current_version_id).values_list(
                    "signer_user_id", flat=True
                )
            )
        else:
            signer_user_ids_raw = []
    if not isinstance(signer_user_ids_raw, list):
        return _json_error("signer_user_ids must be a list", status=400)

    signer_user_ids: list[uuid.UUID] = []
    for raw in signer_user_ids_raw:
        try:
            signer_user_ids.append(uuid.UUID(str(raw)))
        except (TypeError, ValueError):
            return _json_error("signer_user_ids must contain UUIDs", status=400)
    signer_user_ids = list(dict.fromkeys(signer_user_ids))
    if not signer_user_ids:
        return _json_error("signer_user_ids is required", status=400)

    template_version_id_raw = payload.get("template_version_id")
    template_version = None
    if template_version_id_raw is not None and str(template_version_id_raw).strip():
        try:
            template_version_id = uuid.UUID(str(template_version_id_raw))
        except (TypeError, ValueError):
            return _json_error("template_version_id must be a UUID", status=400)
        template_version = TemplateVersion.objects.filter(
            id=template_version_id, template=sow.template
        ).first()
        if template_version is None:
            return _json_error("invalid template_version_id", status=400)
    else:
        template_version = (
            TemplateVersion.objects.filter(
                id=sow.template.current_version_id, template=sow.template
            ).first()
            if sow.template.current_version_id
            else None
        )
        if template_version is None:
            return _json_error("template has no current version", status=400)

    User = get_user_model()
    signer_users = list(User.objects.filter(id__in=signer_user_ids).order_by("created_at"))
    if len(signer_users) != len(signer_user_ids):
        return _json_error("one or more signer_user_ids are invalid", status=400)

    valid_signer_ids = set(
        OrgMembership.objects.filter(
            org=org,
            role=OrgMembership.Role.CLIENT,
            user_id__in=signer_user_ids,
        ).values_list("user_id", flat=True)
    )
    if len(valid_signer_ids) != len(signer_user_ids):
        return _json_error("all signers must be client org members", status=400)

    try:
        version = create_sow_version(
            sow=sow,
            template_version=template_version,
            variables=variables_raw,
            signer_users=signer_users,
            created_by_user=user if membership is not None else None,
        )
    except SoWValidationError as exc:
        return _json_error(exc.message, status=409)

    sow.refresh_from_db(fields=["current_version_id", "updated_at"])
    signers = list(SoWSigner.objects.filter(sow_version=version).order_by("created_at", "id").all())
    return JsonResponse(
        {
            "sow": _sow_dict(sow),
            "version": _version_dict(version, include_body=True),
            "signers": [_signer_dict(s) for s in signers],
        }
    )


@require_http_methods(["GET"])
def sow_detail_view(request: HttpRequest, org_id, sow_id) -> JsonResponse:
    """Fetch the current SoW version, signers, and PDF artifact status.

    Auth: Session-only (see `docs/api/scope-map.yaml` operation `sows__sow_get`). CLIENT access is
    limited to signers on the current version; MEMBER access is forbidden.
    Inputs: Path `org_id`, `sow_id`.
    Returns: `{sow, version, signers, pdf}`.
    Side effects: None.
    """
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    sow = SoW.objects.filter(id=sow_id, org=org).select_related("project", "template").first()
    if sow is None:
        return _json_error("not found", status=404)

    access_err = _require_sow_read_access(user=user, org=org, sow=sow)
    if access_err is not None:
        return access_err

    version = (
        SoWVersion.objects.filter(id=sow.current_version_id, sow=sow).first()
        if sow.current_version_id
        else None
    )
    if version is None:
        return _json_error("not found", status=404)

    signers = list(
        SoWSigner.objects.filter(sow_version=version)
        .select_related("signer_user")
        .order_by("created_at", "id")
    )
    artifact = SoWPdfArtifact.objects.filter(sow_version=version).first()
    membership = _require_membership(user, org)
    redact_for_client = membership is not None and membership.role == OrgMembership.Role.CLIENT
    return JsonResponse(
        {
            "sow": _sow_dict(sow),
            "version": _version_dict(version, include_body=True),
            "signers": [
                _signer_dict_for_viewer(
                    s, viewer_user_id=user.id, redact_for_client=redact_for_client
                )
                for s in signers
            ],
            "pdf": _pdf_artifact_dict(artifact) if artifact is not None else None,
        }
    )


@require_http_methods(["POST"])
def sow_send_view(request: HttpRequest, org_id, sow_id) -> JsonResponse:
    """Move the current SoW version to "pending signature".

    Auth: Session-only (ADMIN/PM) (see `docs/api/scope-map.yaml` operation `sows__sow_send_post`).
    Inputs: Path `org_id`, `sow_id`.
    Returns: `{sow, version, signers}` (version includes rendered body).
    Side effects: Transitions the current version and may trigger downstream notifications.
    """
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_pm_or_admin_membership(user, org)
    if membership is None:
        return _json_error("forbidden", status=403)

    sow = SoW.objects.filter(id=sow_id, org=org).select_related("org").first()
    if sow is None:
        return _json_error("not found", status=404)

    try:
        version = send_sow(sow=sow, actor_user=user)
    except SoWValidationError as exc:
        return _json_error(exc.message, status=409)

    signers = list(SoWSigner.objects.filter(sow_version=version).order_by("created_at", "id").all())
    return JsonResponse(
        {
            "sow": _sow_dict(sow),
            "version": _version_dict(version, include_body=True),
            "signers": [_signer_dict(s) for s in signers],
        }
    )


@require_http_methods(["POST"])
def sow_respond_view(request: HttpRequest, org_id, sow_id) -> JsonResponse:
    """Record a signer decision (approve/reject) for the current SoW version.

    Auth: Session-only (CLIENT signer) (see `docs/api/scope-map.yaml` operation
    `sows__sow_respond_post`).
    Inputs: Path `org_id`, `sow_id`; JSON `{decision, comment?, typed_signature?}`.
    Returns: `{sow, version, signers}` (version includes rendered body).
    Side effects: Updates signer status and may transition the SoW version
    when all responses arrive.
    """
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    membership = _require_membership(user, org)
    if membership is None or membership.role != OrgMembership.Role.CLIENT:
        return _json_error("forbidden", status=403)

    sow = SoW.objects.filter(id=sow_id, org=org).select_related("org").first()
    if sow is None:
        return _json_error("not found", status=404)

    if not ProjectMembership.objects.filter(
        project_id=sow.project_id,
        user_id=membership.user_id,
    ).exists():
        return _json_error("not found", status=404)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    try:
        version = signer_respond(
            sow=sow,
            signer_user=user,
            decision=payload.get("decision"),
            comment=payload.get("comment") or "",
            typed_signature=payload.get("typed_signature") or "",
        )
    except SoWValidationError as exc:
        status = 403 if exc.message == "forbidden" else 409
        return _json_error(exc.message, status=status)

    signers = list(SoWSigner.objects.filter(sow_version=version).order_by("created_at", "id").all())
    return JsonResponse(
        {
            "sow": _sow_dict(sow),
            "version": _version_dict(version, include_body=True),
            "signers": [
                _signer_dict_for_viewer(s, viewer_user_id=user.id, redact_for_client=True)
                for s in signers
            ],
        }
    )


def _sow_pdf_filename(sow: SoW, version: SoWVersion) -> str:
    return f"sow-{sow.id}-v{int(version.version)}.pdf"


@require_http_methods(["GET", "POST"])
def sow_pdf_view(request: HttpRequest, org_id, sow_id) -> HttpResponse:
    """Download a signed SoW PDF, or enqueue PDF rendering.

    Auth: Session-only (see `docs/api/scope-map.yaml` operations `sows__sow_pdf_get` and
    `sows__sow_pdf_post`). CLIENT access is limited to signers on the current version.
    Inputs: Path `org_id`, `sow_id`.
    Returns:
      - GET: PDF file response (409 if not ready).
      - POST: 202 Accepted with PDF artifact status and queued Celery task id (ADMIN/PM only).
    Side effects: POST creates/updates a `SoWPdfArtifact` and may enqueue a Celery render task.
    """
    user, err = _require_session_user(request)
    if err is not None:
        return err

    org = _require_org(org_id)
    if org is None:
        return _json_error("not found", status=404)

    sow = SoW.objects.filter(id=sow_id, org=org).select_related("project", "template").first()
    if sow is None:
        return _json_error("not found", status=404)

    if request.method == "POST":
        membership = _require_pm_or_admin_membership(user, org)
        if membership is None:
            return _json_error("forbidden", status=403)

    access_err = _require_sow_read_access(user=user, org=org, sow=sow)
    if access_err is not None:
        return access_err

    version = (
        SoWVersion.objects.filter(id=sow.current_version_id, sow=sow).first()
        if sow.current_version_id
        else None
    )
    if version is None:
        return _json_error("not found", status=404)

    if version.status != SoWVersion.Status.SIGNED:
        return _json_error("sow is not signed", status=409)

    if request.method == "POST":
        artifact_id = None
        enqueue_needed = True
        with transaction.atomic():
            artifact = (
                SoWPdfArtifact.objects.select_for_update().filter(sow_version=version).first()
            )
            if artifact is None:
                artifact = SoWPdfArtifact.objects.create(sow_version=version)

            if artifact.status == SoWPdfArtifact.Status.RUNNING:
                enqueue_needed = False
            elif (
                artifact.status == SoWPdfArtifact.Status.QUEUED
                and str(artifact.celery_task_id or "").strip()
            ):
                enqueue_needed = False
            else:
                SoWPdfArtifact.objects.filter(id=artifact.id).update(
                    status=SoWPdfArtifact.Status.QUEUED,
                    celery_task_id="",
                    started_at=None,
                    completed_at=None,
                    blocked_urls=[],
                    missing_images=[],
                    error_code="",
                    error_message="",
                    qa_report={},
                )

            artifact_id = str(artifact.id)

        if enqueue_needed:
            async_res = render_sow_version_pdf.delay(artifact_id)
            SoWPdfArtifact.objects.filter(id=artifact_id).update(
                celery_task_id=str(getattr(async_res, "id", "") or "")
            )

        artifact = SoWPdfArtifact.objects.filter(id=artifact_id).first()
        return JsonResponse(
            {"status": "accepted", "pdf": _pdf_artifact_dict(artifact)},
            status=202,
        )

    artifact = SoWPdfArtifact.objects.filter(sow_version=version).first()
    if artifact is None or not artifact.pdf_file:
        return _json_error("pdf not ready", status=409)

    try:
        handle = artifact.pdf_file.open("rb")
    except FileNotFoundError:
        return _json_error("pdf not found", status=404)

    response = FileResponse(
        handle,
        content_type=artifact.pdf_content_type or "application/pdf",
    )
    response["Content-Disposition"] = f'attachment; filename="{_sow_pdf_filename(sow, version)}"'
    return response
