from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.core.files import File
from django.utils import timezone

from realtime.services import publish_org_event

from .models import ReportRun, ReportRunPdfRenderLog
from .pdf_rendering import (
    build_report_pdf_html,
    sanitize_error_message,
    sanitize_render_qa_report,
    sanitize_url_for_log,
)


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _chrome_bin() -> str:
    override = os.environ.get("VIA_RAH_PDF_CHROME_BIN", "").strip()
    if override:
        return override
    candidates = [
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return candidates[0]


def _renderer_script() -> Path:
    return Path(settings.BASE_DIR) / "reports" / "pdf_renderer" / "render.js"


def _renderer_assets_dir() -> Path:
    return Path(settings.BASE_DIR) / "reports" / "pdf_assets"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(8192)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _timeout_seconds() -> int:
    raw = os.environ.get("VIA_RAH_PDF_RENDER_TIMEOUT_SECONDS", "90").strip()
    try:
        return max(int(raw), 1)
    except ValueError:
        return 90


@shared_task
def render_report_run_pdf(render_log_id: str) -> None:
    """Render a report run PDF and persist results to the DB.

    Trigger: Enqueued by `reports.views.report_run_pdf_view` (POST).
    Inputs: `render_log_id` is the `ReportRunPdfRenderLog` UUID (string form).
    Operational notes: Runs the Node/Chromium renderer in a temp dir and captures a QA JSON report.
    Idempotency: Returns early when the log is already RUNNING.
    Re-running will attempt a new render.
    Side effects: Updates the render log status/QA report and stores the PDF + metadata
    on `ReportRun`.
    """
    now = timezone.now()

    render_log = (
        ReportRunPdfRenderLog.objects.select_related(
            "report_run__org", "report_run__project", "report_run__template"
        )
        .filter(id=render_log_id)
        .first()
    )
    if render_log is None:
        return

    if render_log.status in {ReportRunPdfRenderLog.Status.RUNNING}:
        return

    ReportRunPdfRenderLog.objects.filter(id=render_log.id).update(
        status=ReportRunPdfRenderLog.Status.RUNNING,
        started_at=now,
    )

    report_run = render_log.report_run
    publish_org_event(
        org_id=report_run.org_id,
        event_type="report_run.pdf_render_log.updated",
        data={
            "report_run_id": str(report_run.id),
            "render_log_id": str(render_log.id),
            "status": ReportRunPdfRenderLog.Status.RUNNING,
        },
    )

    chrome_bin = _chrome_bin()
    renderer_script = _renderer_script()
    assets_dir = _renderer_assets_dir()

    error_code = ""
    error_message = ""
    blocked_urls: list[str] = []
    missing_images: list[str] = []
    qa_report: dict = {}
    pdf_content_type = "application/pdf"

    try:
        html = build_report_pdf_html(report_run=report_run)
    except Exception as exc:  # noqa: BLE001
        error_code = "build_html_failed"
        error_message = sanitize_error_message(str(exc))
        ReportRunPdfRenderLog.objects.filter(id=render_log.id).update(
            status=ReportRunPdfRenderLog.Status.FAILED,
            completed_at=timezone.now(),
            error_code=error_code,
            error_message=error_message,
        )
        publish_org_event(
            org_id=report_run.org_id,
            event_type="report_run.pdf_render_log.updated",
            data={
                "report_run_id": str(report_run.id),
                "render_log_id": str(render_log.id),
                "status": ReportRunPdfRenderLog.Status.FAILED,
            },
        )
        return

    with tempfile.TemporaryDirectory(prefix="viarah_report_pdf_") as tmp_dir:
        tmp = Path(tmp_dir)
        html_path = tmp / "report.html"
        pdf_path = tmp / "report.pdf"
        qa_json_path = tmp / "render.json"

        html_path.write_text(html, encoding="utf-8")

        cmd = [
            "node",
            str(renderer_script),
            "--html",
            str(html_path),
            "--out-pdf",
            str(pdf_path),
            "--out-report-json",
            str(qa_json_path),
            "--assets-dir",
            str(assets_dir),
            "--chrome",
            chrome_bin,
        ]

        env = os.environ.copy()
        if _truthy_env("VIA_RAH_PDF_NO_SANDBOX") or _truthy_env("VL_MD2PDF_NO_SANDBOX"):
            env["VIA_RAH_PDF_NO_SANDBOX"] = "1"

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=_timeout_seconds(),
                check=False,
            )
        except FileNotFoundError as exc:
            error_code = "renderer_missing_dependency"
            error_message = sanitize_error_message(str(exc))
            proc = None
        except subprocess.TimeoutExpired:
            error_code = "renderer_timeout"
            error_message = "PDF renderer timed out"
            proc = None
        except Exception as exc:  # noqa: BLE001
            error_code = "renderer_failed"
            error_message = sanitize_error_message(str(exc))
            proc = None

        raw_report: object = {}
        if qa_json_path.exists():
            try:
                raw_report = json.loads(qa_json_path.read_text(encoding="utf-8") or "{}")
            except json.JSONDecodeError:
                raw_report = {}

        qa_report = sanitize_render_qa_report(raw_report)

        blocked_urls_raw = qa_report.get("blocked_requests")
        if isinstance(blocked_urls_raw, list):
            blocked_urls = [
                sanitize_url_for_log(str(u)) for u in blocked_urls_raw if str(u).strip()
            ]

        missing_images_raw = qa_report.get("missing_images")
        if isinstance(missing_images_raw, list):
            missing_images = [
                sanitize_url_for_log(str(u)) for u in missing_images_raw if str(u).strip()
            ]

        if proc is not None and proc.returncode != 0 and not error_code:
            error_code = (
                str(qa_report.get("error_code") or "").strip() or f"renderer_exit_{proc.returncode}"
            )
            error_message = sanitize_error_message(
                str(qa_report.get("error_message") or proc.stderr or proc.stdout or "").strip()
            )

        if blocked_urls and not error_code:
            error_code = "blocked_remote_requests"
            error_message = "blocked remote requests during render"

        if missing_images and not error_code:
            error_code = "missing_images"
            error_message = "one or more images failed to load"

        if error_code:
            ReportRunPdfRenderLog.objects.filter(id=render_log.id).update(
                status=ReportRunPdfRenderLog.Status.FAILED,
                completed_at=timezone.now(),
                blocked_urls=blocked_urls[:200],
                missing_images=missing_images[:200],
                error_code=error_code,
                error_message=error_message,
                qa_report=qa_report,
            )
            publish_org_event(
                org_id=report_run.org_id,
                event_type="report_run.pdf_render_log.updated",
                data={
                    "report_run_id": str(report_run.id),
                    "render_log_id": str(render_log.id),
                    "status": ReportRunPdfRenderLog.Status.FAILED,
                },
            )
            return

        if not pdf_path.exists():
            ReportRunPdfRenderLog.objects.filter(id=render_log.id).update(
                status=ReportRunPdfRenderLog.Status.FAILED,
                completed_at=timezone.now(),
                blocked_urls=blocked_urls[:200],
                missing_images=missing_images[:200],
                error_code="pdf_missing",
                error_message="renderer did not produce a PDF",
                qa_report=qa_report,
            )
            publish_org_event(
                org_id=report_run.org_id,
                event_type="report_run.pdf_render_log.updated",
                data={
                    "report_run_id": str(report_run.id),
                    "render_log_id": str(render_log.id),
                    "status": ReportRunPdfRenderLog.Status.FAILED,
                },
            )
            return

        sha256 = _sha256_file(pdf_path)
        size_bytes = pdf_path.stat().st_size

        with pdf_path.open("rb") as handle:
            report_run.pdf_file.save("report.pdf", File(handle), save=False)
        ReportRun.objects.filter(id=report_run.id).update(
            pdf_file=report_run.pdf_file.name,
            pdf_content_type=pdf_content_type,
            pdf_size_bytes=size_bytes,
            pdf_sha256=sha256,
            pdf_rendered_at=timezone.now(),
        )

        ReportRunPdfRenderLog.objects.filter(id=render_log.id).update(
            status=ReportRunPdfRenderLog.Status.SUCCESS,
            completed_at=timezone.now(),
            blocked_urls=blocked_urls[:200],
            missing_images=missing_images[:200],
            error_code="",
            error_message="",
            qa_report=qa_report,
        )
        publish_org_event(
            org_id=report_run.org_id,
            event_type="report_run.pdf_render_log.updated",
            data={
                "report_run_id": str(report_run.id),
                "render_log_id": str(render_log.id),
                "status": ReportRunPdfRenderLog.Status.SUCCESS,
            },
        )
