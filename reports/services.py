from __future__ import annotations

import datetime
import html
import re

from django.db import transaction

from collaboration.services import render_markdown_to_safe_html
from core.liquid import liquid_environment
from work_items.models import Epic, Project, Subtask, Task, WorkItemStatus

from .models import ReportRun

MAX_RENDERED_MARKDOWN_CHARS = 200_000
MAX_RENDERED_HTML_CHARS = 400_000

_ISO_DATE_RE = re.compile(r"^\\d{4}-\\d{2}-\\d{2}$")

_LIQUID_ENV = liquid_environment()


class ReportValidationError(Exception):
    """Raised when report inputs/templates cannot be validated or rendered safely."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _parse_date(value, field: str) -> datetime.date:
    if not isinstance(value, str):
        raise ReportValidationError(f"{field} must be YYYY-MM-DD")
    value_str = value.strip()
    if not value_str or not _ISO_DATE_RE.fullmatch(value_str):
        raise ReportValidationError(f"{field} must be YYYY-MM-DD")
    try:
        return datetime.date.fromisoformat(value_str)
    except ValueError as exc:
        raise ReportValidationError(f"{field} must be a valid date") from exc


def normalize_scope(scope_raw: object) -> dict:
    """Validate and normalize a report scope object.

    Supported keys: `from_date`, `to_date`, and `statuses`. Dates are normalized to ISO strings.
    """
    if scope_raw is None:
        raise ReportValidationError("scope is required")
    if not isinstance(scope_raw, dict):
        raise ReportValidationError("scope must be an object")

    allowed_keys = {"from_date", "to_date", "statuses"}
    extra_keys = set(scope_raw.keys()) - allowed_keys
    if extra_keys:
        raise ReportValidationError("scope contains unknown keys")

    from_date = scope_raw.get("from_date")
    to_date = scope_raw.get("to_date")
    statuses_raw = scope_raw.get("statuses")

    normalized: dict[str, object] = {}
    from_dt = None
    to_dt = None

    if from_date is not None:
        from_dt = _parse_date(from_date, "from_date")
        normalized["from_date"] = from_dt.isoformat()
    if to_date is not None:
        to_dt = _parse_date(to_date, "to_date")
        normalized["to_date"] = to_dt.isoformat()
    if from_dt is not None and to_dt is not None and from_dt > to_dt:
        raise ReportValidationError("from_date must be <= to_date")

    if statuses_raw is not None:
        if not isinstance(statuses_raw, list):
            raise ReportValidationError("statuses must be a list")
        statuses: list[str] = []
        for raw in statuses_raw:
            value = str(raw).strip()
            if value not in set(WorkItemStatus.values):
                raise ReportValidationError("statuses contains invalid status")
            statuses.append(value)
        if statuses:
            normalized["statuses"] = statuses

    return normalized


def _epic_dict(epic: Epic) -> dict:
    return {
        "id": str(epic.id),
        "project_id": str(epic.project_id),
        "title": epic.title,
        "description": epic.description,
        "status": epic.status,
        "created_at": epic.created_at.isoformat(),
        "updated_at": epic.updated_at.isoformat(),
    }


def _task_dict(task: Task) -> dict:
    return {
        "id": str(task.id),
        "epic_id": str(task.epic_id),
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "start_date": task.start_date.isoformat() if task.start_date else None,
        "end_date": task.end_date.isoformat() if task.end_date else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def _subtask_dict(subtask: Subtask) -> dict:
    return {
        "id": str(subtask.id),
        "task_id": str(subtask.task_id),
        "title": subtask.title,
        "description": subtask.description,
        "status": subtask.status,
        "start_date": subtask.start_date.isoformat() if subtask.start_date else None,
        "end_date": subtask.end_date.isoformat() if subtask.end_date else None,
        "created_at": subtask.created_at.isoformat(),
        "updated_at": subtask.updated_at.isoformat(),
    }


def _project_client_safe_dict(project: Project) -> dict:
    return {
        "id": str(project.id),
        "org_id": str(project.org_id),
        "name": project.name,
        "updated_at": project.updated_at.isoformat(),
    }


def _epic_client_safe_dict(epic: Epic) -> dict:
    return {
        "id": str(epic.id),
        "project_id": str(epic.project_id),
        "title": epic.title,
        "status": epic.status,
    }


def _task_client_safe_dict(task: Task) -> dict:
    return {
        "id": str(task.id),
        "epic_id": str(task.epic_id),
        "title": task.title,
        "status": task.status,
        "start_date": task.start_date.isoformat() if task.start_date else None,
        "end_date": task.end_date.isoformat() if task.end_date else None,
        "updated_at": task.updated_at.isoformat(),
    }


def _subtask_client_safe_dict(subtask: Subtask) -> dict:
    return {
        "id": str(subtask.id),
        "task_id": str(subtask.task_id),
        "workflow_stage_id": (
            str(subtask.workflow_stage_id) if subtask.workflow_stage_id else None
        ),
        "title": subtask.title,
        "status": subtask.status,
        "start_date": subtask.start_date.isoformat() if subtask.start_date else None,
        "end_date": subtask.end_date.isoformat() if subtask.end_date else None,
    }


def build_report_context(*, org, project: Project, scope: dict) -> dict:
    """Build the internal report context (full-fidelity tasks/subtasks) for Liquid rendering."""
    epics = list(Epic.objects.filter(project=project).order_by("created_at"))

    tasks_qs = Task.objects.filter(epic__project=project)
    subtasks_qs = Subtask.objects.filter(task__epic__project=project)

    statuses = scope.get("statuses") or []
    if statuses:
        tasks_qs = tasks_qs.filter(status__in=statuses)
        subtasks_qs = subtasks_qs.filter(status__in=statuses)

    from_date_raw = scope.get("from_date")
    to_date_raw = scope.get("to_date")
    if from_date_raw:
        from_dt = datetime.date.fromisoformat(str(from_date_raw))
        tasks_qs = tasks_qs.filter(updated_at__date__gte=from_dt)
        subtasks_qs = subtasks_qs.filter(updated_at__date__gte=from_dt)
    if to_date_raw:
        to_dt = datetime.date.fromisoformat(str(to_date_raw))
        tasks_qs = tasks_qs.filter(updated_at__date__lte=to_dt)
        subtasks_qs = subtasks_qs.filter(updated_at__date__lte=to_dt)

    tasks = list(tasks_qs.order_by("updated_at", "created_at", "id"))
    subtasks = list(subtasks_qs.order_by("updated_at", "created_at", "id"))

    tasks_payload = [_task_dict(t) for t in tasks]
    subtasks_payload = [_subtask_dict(s) for s in subtasks]

    tasks_by_status: dict[str, list[dict]] = {}
    for task in tasks_payload:
        tasks_by_status.setdefault(task["status"], []).append(task)

    return {
        "org": {"id": str(org.id), "name": org.name},
        "project": {
            "id": str(project.id),
            "name": project.name,
            "description": project.description,
        },
        "scope": scope,
        "epics": [_epic_dict(e) for e in epics],
        "tasks": tasks_payload,
        "subtasks": subtasks_payload,
        "tasks_by_status": tasks_by_status,
    }


def build_public_report_context(*, org, project: Project, scope: dict) -> dict:
    """Build a client-safe report context (client_safe tasks/subtasks only) for sharing."""
    tasks_qs = Task.objects.filter(epic__project=project, client_safe=True)
    subtasks_qs = Subtask.objects.filter(task__epic__project=project, task__client_safe=True)

    statuses = scope.get("statuses") or []
    if statuses:
        tasks_qs = tasks_qs.filter(status__in=statuses)
        subtasks_qs = subtasks_qs.filter(status__in=statuses)

    from_date_raw = scope.get("from_date")
    to_date_raw = scope.get("to_date")
    if from_date_raw:
        from_dt = datetime.date.fromisoformat(str(from_date_raw))
        tasks_qs = tasks_qs.filter(updated_at__date__gte=from_dt)
        subtasks_qs = subtasks_qs.filter(updated_at__date__gte=from_dt)
    if to_date_raw:
        to_dt = datetime.date.fromisoformat(str(to_date_raw))
        tasks_qs = tasks_qs.filter(updated_at__date__lte=to_dt)
        subtasks_qs = subtasks_qs.filter(updated_at__date__lte=to_dt)

    tasks = list(tasks_qs.order_by("updated_at", "created_at", "id"))
    subtasks = list(subtasks_qs.order_by("updated_at", "created_at", "id"))

    tasks_payload = [_task_client_safe_dict(t) for t in tasks]
    subtasks_payload = [_subtask_client_safe_dict(s) for s in subtasks]

    epic_ids = list({t.epic_id for t in tasks})
    epics = list(Epic.objects.filter(project=project, id__in=epic_ids).order_by("created_at"))

    tasks_by_status: dict[str, list[dict]] = {}
    for task in tasks_payload:
        tasks_by_status.setdefault(task["status"], []).append(task)

    return {
        "org": {"id": str(org.id), "name": org.name},
        "project": _project_client_safe_dict(project),
        "scope": scope,
        "epics": [_epic_client_safe_dict(e) for e in epics],
        "tasks": tasks_payload,
        "subtasks": subtasks_payload,
        "tasks_by_status": tasks_by_status,
    }


def render_report_markdown(*, template_body: str, context: dict) -> str:
    """Render a Liquid template into markdown and enforce size limits."""
    try:
        liquid_template = _LIQUID_ENV.from_string(template_body or "")
        rendered = liquid_template.render(**context)
    except Exception as exc:  # noqa: BLE001
        raise ReportValidationError("failed to render Liquid template") from exc

    if len(rendered) > MAX_RENDERED_MARKDOWN_CHARS:
        raise ReportValidationError("rendered output is too large")

    return rendered.strip()


def create_report_run(
    *,
    org,
    project: Project,
    template,
    template_version,
    scope: dict,
    created_by_user,
) -> ReportRun:
    """Create a `ReportRun` by rendering the report template to markdown + safe HTML."""
    context = build_report_context(org=org, project=project, scope=scope)
    output_markdown = render_report_markdown(template_body=template_version.body, context=context)
    output_html = render_markdown_to_safe_html(output_markdown)

    if len(output_html) > MAX_RENDERED_HTML_CHARS:
        raise ReportValidationError("rendered output is too large")

    with transaction.atomic():
        report_run = ReportRun.objects.create(
            org=org,
            project=project,
            template=template,
            template_version=template_version,
            scope=scope,
            output_markdown=output_markdown,
            output_html=output_html,
            created_by_user=created_by_user,
        )

    return report_run


def build_web_view_html(*, report_run: ReportRun) -> str:
    """Wrap a report run's rendered HTML in a minimal standalone HTML document."""
    title = html.escape(f"Report Run {report_run.id}")
    return (
        "<!doctype html>"
        "<html>"
        "<head>"
        '<meta charset="utf-8">'
        f"<title>{title}</title>"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "</head>"
        f"<body>{report_run.output_html}</body>"
        "</html>"
    )
