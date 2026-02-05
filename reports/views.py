from __future__ import annotations

import json
import uuid

from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from audit.services import write_audit_event
from identity.models import Org, OrgMembership
from templates.models import Template, TemplateType, TemplateVersion
from work_items.models import Project

from .models import ReportRun, ReportRunPdfRenderLog
from .services import (
    ReportValidationError,
    build_web_view_html,
    create_report_run,
    normalize_scope,
)
from .tasks import render_report_run_pdf


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


def _principal_project_id(principal) -> uuid.UUID | None:
    project_id = getattr(principal, "project_id", None)
    if project_id is None or not str(project_id).strip():
        return None
    try:
        return uuid.UUID(str(project_id))
    except (TypeError, ValueError):
        return None


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

    membership = (
        OrgMembership.objects.filter(user=user, org=org, role__in=allowed_roles)
        .select_related("org")
        .first()
    )
    if membership is None:
        return org, None, None, _json_error("forbidden", status=403)

    return org, membership, None, None


def _report_run_dict(report_run: ReportRun, *, include_outputs: bool = False) -> dict:
    payload = {
        "id": str(report_run.id),
        "org_id": str(report_run.org_id),
        "project_id": str(report_run.project_id),
        "template_id": str(report_run.template_id),
        "template_version_id": str(report_run.template_version_id),
        "scope": report_run.scope,
        "created_by_user_id": (
            str(report_run.created_by_user_id) if report_run.created_by_user_id else None
        ),
        "created_at": report_run.created_at.isoformat(),
    }
    if include_outputs:
        payload["output_markdown"] = report_run.output_markdown
        payload["output_html"] = report_run.output_html
    return payload


def _web_view_url(request: HttpRequest, org_id, report_run_id: uuid.UUID) -> str:
    return request.build_absolute_uri(f"/api/orgs/{org_id}/report-runs/{report_run_id}/web-view")


@require_http_methods(["GET", "POST"])
def report_runs_collection_view(request: HttpRequest, org_id) -> JsonResponse:
    """List or create report runs for a project.

    Auth: Session or API key (see `docs/api/scope-map.yaml` operations
    `reports__report_runs_get` and `reports__report_runs_post`). API keys may be project-restricted.
    Inputs:
      - GET: Path `org_id`; query `project_id` (required).
      - POST: Path `org_id`; JSON `{project_id, template_id, template_version_id?, scope}`.
    Returns: `{report_runs: [...]}` for GET; `{report_run}` for POST
    (includes output + web view URL).
    Side effects: POST creates a report run and writes an audit event.
    """
    required_scope = "read" if request.method == "GET" else "write"
    roles = {OrgMembership.Role.ADMIN, OrgMembership.Role.PM, OrgMembership.Role.MEMBER}
    if request.method != "GET":
        roles = {OrgMembership.Role.ADMIN, OrgMembership.Role.PM}

    org, membership, principal, err = _require_org_access(
        request, org_id, required_scope=required_scope, allowed_roles=roles
    )
    if err is not None:
        return err

    if request.method == "GET":
        project_id_raw = request.GET.get("project_id", "").strip()
        if not project_id_raw:
            return _json_error("project_id is required", status=400)
        try:
            project_id = uuid.UUID(project_id_raw)
        except (TypeError, ValueError):
            return _json_error("project_id must be a UUID", status=400)

        if principal is not None:
            project_id_restriction = _principal_project_id(principal)
            if project_id_restriction is not None and project_id_restriction != project_id:
                return _json_error("forbidden", status=403)

        if not Project.objects.filter(id=project_id, org=org).exists():
            return _json_error("not found", status=404)

        runs = ReportRun.objects.filter(org=org, project_id=project_id).order_by(
            "-created_at", "-id"
        )
        return JsonResponse(
            {
                "report_runs": [
                    {**_report_run_dict(r), "web_view_url": _web_view_url(request, org.id, r.id)}
                    for r in runs
                ]
            }
        )

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    project_id_raw = str(payload.get("project_id", "")).strip()
    template_id_raw = str(payload.get("template_id", "")).strip()
    template_version_id_raw = payload.get("template_version_id")

    if not project_id_raw:
        return _json_error("project_id is required", status=400)
    if not template_id_raw:
        return _json_error("template_id is required", status=400)

    try:
        project_id = uuid.UUID(project_id_raw)
    except (TypeError, ValueError):
        return _json_error("project_id must be a UUID", status=400)

    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None and project_id_restriction != project_id:
            return _json_error("forbidden", status=403)

    try:
        template_id = uuid.UUID(template_id_raw)
    except (TypeError, ValueError):
        return _json_error("template_id must be a UUID", status=400)

    template = Template.objects.filter(id=template_id, org=org).first()
    if template is None:
        return _json_error("not found", status=404)
    if template.type != TemplateType.REPORT:
        return _json_error("template must be a report template", status=400)

    project = Project.objects.filter(id=project_id, org=org).first()
    if project is None:
        return _json_error("not found", status=404)

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

    try:
        scope = normalize_scope(payload.get("scope"))
    except ReportValidationError as exc:
        return _json_error(exc.message, status=400)

    try:
        report_run = create_report_run(
            org=org,
            project=project,
            template=template,
            template_version=template_version,
            scope=scope,
            created_by_user=request.user if membership is not None else None,
        )
    except ReportValidationError as exc:
        return _json_error(exc.message, status=400)

    write_audit_event(
        org=org,
        actor_user=request.user if membership is not None else None,
        event_type="report_run.created",
        metadata={
            "report_run_id": str(report_run.id),
            "project_id": str(project.id),
            "template_id": str(template.id),
            "template_version_id": str(template_version.id),
        },
    )

    return JsonResponse(
        {
            "report_run": {
                **_report_run_dict(report_run, include_outputs=True),
                "web_view_url": _web_view_url(request, org.id, report_run.id),
            }
        }
    )


@require_http_methods(["GET"])
def report_run_detail_view(request: HttpRequest, org_id, report_run_id) -> JsonResponse:
    """Fetch a single report run (including rendered outputs).

    Auth: Session or API key (read) (see `docs/api/scope-map.yaml` operation
    `reports__report_run_get`).
    API keys may be project-restricted.
    Inputs: Path `org_id`, `report_run_id`.
    Returns: `{report_run}` (includes output markdown/html + web view URL).
    Side effects: None.
    """
    org, _membership, principal, err = _require_org_access(
        request,
        org_id,
        required_scope="read",
        allowed_roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM, OrgMembership.Role.MEMBER},
    )
    if err is not None:
        return err

    report_run = ReportRun.objects.filter(id=report_run_id, org=org).first()
    if report_run is None:
        return _json_error("not found", status=404)

    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None and project_id_restriction != report_run.project_id:
            return _json_error("forbidden", status=403)

    return JsonResponse(
        {
            "report_run": {
                **_report_run_dict(report_run, include_outputs=True),
                "web_view_url": _web_view_url(request, org.id, report_run.id),
            }
        }
    )


@require_http_methods(["POST"])
def report_run_regenerate_view(request: HttpRequest, org_id, report_run_id) -> JsonResponse:
    """Regenerate a report run (creates a new run with the same scope).

    Auth: Session or API key (write) (see `docs/api/scope-map.yaml` operation
    `reports__report_run_regenerate_post`). API keys may be project-restricted.
    Inputs: Path `org_id`, `report_run_id`; optional JSON `{template_version_id?}`.
    Returns: `{report_run}` (new run; includes output + web view URL).
    Side effects: Creates a new report run and writes an audit event.
    """
    org, membership, principal, err = _require_org_access(
        request,
        org_id,
        required_scope="write",
        allowed_roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM},
    )
    if err is not None:
        return err

    prior_run = (
        ReportRun.objects.filter(id=report_run_id, org=org)
        .select_related("project", "template")
        .first()
    )
    if prior_run is None:
        return _json_error("not found", status=404)

    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None and project_id_restriction != prior_run.project_id:
            return _json_error("forbidden", status=403)

    try:
        payload = _parse_json(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    template = prior_run.template
    template_version_id_raw = payload.get("template_version_id")

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

    try:
        report_run = create_report_run(
            org=org,
            project=prior_run.project,
            template=template,
            template_version=template_version,
            scope=prior_run.scope,
            created_by_user=request.user if membership is not None else None,
        )
    except ReportValidationError as exc:
        return _json_error(exc.message, status=400)

    write_audit_event(
        org=org,
        actor_user=request.user if membership is not None else None,
        event_type="report_run.regenerated",
        metadata={
            "prior_report_run_id": str(prior_run.id),
            "report_run_id": str(report_run.id),
            "project_id": str(prior_run.project_id),
            "template_id": str(template.id),
            "template_version_id": str(template_version.id),
        },
    )

    return JsonResponse(
        {
            "report_run": {
                **_report_run_dict(report_run, include_outputs=True),
                "web_view_url": _web_view_url(request, org.id, report_run.id),
            }
        }
    )


@require_http_methods(["GET"])
def report_run_web_view(request: HttpRequest, org_id, report_run_id) -> HttpResponse:
    """Return an HTML web view for a report run.

    Auth: Session or API key (read) (see `docs/api/scope-map.yaml` operation
    `reports__report_run_web_view_get`). API keys may be project-restricted.
    Inputs: Path `org_id`, `report_run_id`.
    Returns: HTML response.
    Side effects: None.
    """
    org, _membership, principal, err = _require_org_access(
        request,
        org_id,
        required_scope="read",
        allowed_roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM, OrgMembership.Role.MEMBER},
    )
    if err is not None:
        return err

    report_run = ReportRun.objects.filter(id=report_run_id, org=org).first()
    if report_run is None:
        return HttpResponse("not found", status=404, content_type="text/plain")

    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None and project_id_restriction != report_run.project_id:
            return HttpResponse("forbidden", status=403, content_type="text/plain")

    html = build_web_view_html(report_run=report_run)
    return HttpResponse(html, content_type="text/html")


def _report_run_pdf_filename(report_run: ReportRun) -> str:
    return f"report-{report_run.id}.pdf"


def _render_log_dict(render_log: ReportRunPdfRenderLog) -> dict:
    return {
        "id": str(render_log.id),
        "report_run_id": str(render_log.report_run_id),
        "status": render_log.status,
        "celery_task_id": render_log.celery_task_id or None,
        "created_at": render_log.created_at.isoformat(),
        "started_at": render_log.started_at.isoformat() if render_log.started_at else None,
        "completed_at": render_log.completed_at.isoformat() if render_log.completed_at else None,
        "blocked_urls": list(render_log.blocked_urls or []),
        "missing_images": list(render_log.missing_images or []),
        "error_code": render_log.error_code or None,
        "error_message": render_log.error_message or None,
        "qa_report": render_log.qa_report or {},
    }


@require_http_methods(["GET", "POST"])
def report_run_pdf_view(request: HttpRequest, org_id, report_run_id) -> HttpResponse:
    """Fetch a report run PDF, or enqueue PDF rendering.

    Auth: Session or API key (see `docs/api/scope-map.yaml` operations `reports__report_run_pdf_get`
    and `reports__report_run_pdf_post`). API keys may be project-restricted.
    Inputs: Path `org_id`, `report_run_id`.
    Returns:
      - GET: PDF file response (409 if not ready).
      - POST: 202 Accepted with `{render_log}` and queued Celery task id.
    Side effects: POST creates a render-log row, enqueues a Celery task, and writes an audit event.
    """
    required_scope = "read" if request.method == "GET" else "write"
    roles = {OrgMembership.Role.ADMIN, OrgMembership.Role.PM, OrgMembership.Role.MEMBER}
    if request.method != "GET":
        roles = {OrgMembership.Role.ADMIN, OrgMembership.Role.PM}

    org, membership, principal, err = _require_org_access(
        request, org_id, required_scope=required_scope, allowed_roles=roles
    )
    if err is not None:
        return err

    report_run = (
        ReportRun.objects.filter(id=report_run_id, org=org).select_related("project").first()
    )
    if report_run is None:
        return _json_error("not found", status=404)

    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None and project_id_restriction != report_run.project_id:
            return _json_error("forbidden", status=403)

    if request.method == "POST":
        render_log = ReportRunPdfRenderLog.objects.create(
            report_run=report_run,
            status=ReportRunPdfRenderLog.Status.QUEUED,
        )
        async_res = render_report_run_pdf.delay(str(render_log.id))
        ReportRunPdfRenderLog.objects.filter(id=render_log.id).update(
            celery_task_id=str(async_res.id or "")
        )

        write_audit_event(
            org=org,
            actor_user=request.user if membership is not None else None,
            event_type="report_run.pdf_requested",
            metadata={
                "report_run_id": str(report_run.id),
                "project_id": str(report_run.project_id),
                "render_log_id": str(render_log.id),
            },
        )

        payload = _render_log_dict(
            ReportRunPdfRenderLog.objects.filter(id=render_log.id).first() or render_log
        )
        return JsonResponse({"status": "accepted", "render_log": payload}, status=202)

    if not report_run.pdf_file:
        return _json_error("pdf not ready", status=409)

    try:
        handle = report_run.pdf_file.open("rb")
    except FileNotFoundError:
        return _json_error("pdf not found", status=404)

    response = FileResponse(
        handle,
        content_type=report_run.pdf_content_type or "application/pdf",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{_report_run_pdf_filename(report_run)}"'
    )
    return response


@require_http_methods(["GET"])
def report_run_pdf_render_logs_view(request: HttpRequest, org_id, report_run_id) -> JsonResponse:
    """List recent PDF render logs for a report run.

    Auth: Session or API key (read) (see `docs/api/scope-map.yaml` operation
    `reports__report_run_render_logs_get`). API keys may be project-restricted.
    Inputs: Path `org_id`, `report_run_id`.
    Returns: `{render_logs: [...]}` (up to 50, newest first).
    Side effects: None.
    """
    org, _membership, principal, err = _require_org_access(
        request,
        org_id,
        required_scope="read",
        allowed_roles={OrgMembership.Role.ADMIN, OrgMembership.Role.PM},
    )
    if err is not None:
        return err

    report_run = ReportRun.objects.filter(id=report_run_id, org=org).first()
    if report_run is None:
        return _json_error("not found", status=404)

    if principal is not None:
        project_id_restriction = _principal_project_id(principal)
        if project_id_restriction is not None and project_id_restriction != report_run.project_id:
            return _json_error("forbidden", status=403)

    logs = (
        ReportRunPdfRenderLog.objects.filter(report_run=report_run)
        .order_by("-created_at")
        .all()[:50]
    )
    return JsonResponse({"render_logs": [_render_log_dict(log) for log in list(logs)]})
