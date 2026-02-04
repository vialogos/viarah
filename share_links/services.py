from __future__ import annotations

import hashlib
import html
import ipaddress
import logging
import secrets
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from collaboration.services import render_markdown_to_safe_html
from notifications.services import emit_report_published
from reports.models import ReportRun
from reports.services import (
    MAX_RENDERED_HTML_CHARS,
    ReportValidationError,
    build_public_report_context,
    render_report_markdown,
)

from .models import ShareLink, ShareLinkAccessLog

logger = logging.getLogger(__name__)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def default_expires_at():
    return timezone.now() + timedelta(days=7)


def create_share_link(
    *,
    org,
    report_run: ReportRun,
    expires_at,
    created_by_user=None,
    created_by_api_key=None,
) -> tuple[ShareLink, str]:
    if (created_by_user is None) == (created_by_api_key is None):
        raise ValueError("exactly one of created_by_user or created_by_api_key is required")

    context = build_public_report_context(
        org=org, project=report_run.project, scope=report_run.scope
    )
    output_markdown = render_report_markdown(
        template_body=report_run.template_version.body, context=context
    )
    output_html = render_markdown_to_safe_html(output_markdown)
    if len(output_html) > MAX_RENDERED_HTML_CHARS:
        raise ReportValidationError("rendered output is too large")

    for _ in range(10):
        raw_token = new_token()
        token_hash = hash_token(raw_token)
        try:
            with transaction.atomic():
                share_link = ShareLink.objects.create(
                    org=org,
                    report_run=report_run,
                    token_hash=token_hash,
                    expires_at=expires_at,
                    created_by_user=created_by_user,
                    created_by_api_key=created_by_api_key,
                    output_markdown=output_markdown,
                    output_html=output_html,
                )

            def _emit() -> None:
                try:
                    emit_report_published(
                        org=org,
                        project=report_run.project,
                        actor_user=created_by_user,
                        report_run_id=str(report_run.id),
                        share_link_id=str(share_link.id),
                        expires_at=share_link.expires_at,
                    )
                except Exception:
                    logger.exception(
                        "report.published emission failed",
                        extra={
                            "org_id": str(org.id),
                            "project_id": str(report_run.project_id),
                            "report_run_id": str(report_run.id),
                            "share_link_id": str(share_link.id),
                        },
                    )

            _emit()
            return share_link, raw_token
        except IntegrityError:
            continue

    raise RuntimeError("failed to mint unique share link token")


def revoke_share_link(*, share_link: ShareLink) -> None:
    if share_link.revoked_at is not None:
        return
    share_link.revoked_at = timezone.now()
    share_link.save(update_fields=["revoked_at"])


def resolve_active_share_link(*, token: str) -> ShareLink | None:
    raw = token.strip()
    if not raw:
        return None

    now = timezone.now()
    token_hash = hash_token(raw)
    return (
        ShareLink.objects.filter(
            token_hash=token_hash,
            revoked_at__isnull=True,
            expires_at__gt=now,
        )
        .only("id", "report_run_id", "output_html")
        .first()
    )


def _normalize_ip(ip_raw: str | None) -> str | None:
    if not ip_raw:
        return None
    try:
        return str(ipaddress.ip_address(ip_raw.strip()))
    except ValueError:
        return None


def _normalize_user_agent(user_agent_raw: str | None) -> str:
    return str(user_agent_raw or "").strip()[:512]


def record_share_link_access(
    *, share_link: ShareLink, ip_address: str | None, user_agent: str | None
) -> ShareLinkAccessLog:
    now = timezone.now()
    normalized_ip = _normalize_ip(ip_address)
    normalized_ua = _normalize_user_agent(user_agent)
    with transaction.atomic():
        log = ShareLinkAccessLog.objects.create(
            share_link=share_link,
            ip_address=normalized_ip,
            user_agent=normalized_ua,
        )
        ShareLink.objects.filter(id=share_link.id).update(
            last_access_at=now,
            access_count=F("access_count") + 1,
        )
    return log


def build_public_share_link_html(*, share_link: ShareLink) -> str:
    title = html.escape(f"Shared Report {share_link.report_run_id}")
    return (
        "<!doctype html>"
        "<html>"
        "<head>"
        '<meta charset="utf-8">'
        f"<title>{title}</title>"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "</head>"
        f"<body>{share_link.output_html}</body>"
        "</html>"
    )
