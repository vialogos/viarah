from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import bleach
from django.conf import settings
from markdown_it import MarkdownIt

from .models import ReportRun

_SENSITIVE_KEY_SUBSTRINGS = {
    "token",
    "password",
    "secret",
    "api_key",
    "apikey",
    "authorization",
}

_URL_RE = re.compile(r"https?://[^\s)\]}>\"']+")

_PDF_MD = MarkdownIt("commonmark", {"html": False})

_PDF_ALLOWED_TAGS = [
    "a",
    "blockquote",
    "br",
    "code",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "ul",
]

_PDF_ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title"],
}

_PDF_ALLOWED_PROTOCOLS = ["http", "https", "mailto", "data", "file"]


def sanitize_inline_svg(svg: str) -> str:
    return (
        str(svg)
        .replace('<?xml version="1.0" encoding="UTF-8" standalone="no"?>', "")
        .replace('<?xml version="1.0" encoding="UTF-8"?>', "")
        .replace("<!DOCTYPE svg>", "")
        .strip()
    )


def _assets_dir() -> Path:
    return Path(settings.BASE_DIR) / "reports" / "pdf_assets"


def _read_asset_text(filename: str) -> str:
    path = _assets_dir() / filename
    return path.read_text(encoding="utf-8")


def render_report_markdown_to_pdf_html(markdown: str) -> str:
    raw_html = _PDF_MD.render(markdown or "")
    return bleach.clean(
        raw_html,
        tags=_PDF_ALLOWED_TAGS,
        attributes=_PDF_ALLOWED_ATTRIBUTES,
        protocols=_PDF_ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    ).strip()


def build_report_pdf_html(*, report_run: ReportRun) -> str:
    vialogos_logo_svg = sanitize_inline_svg(_read_asset_text("via-logos-logo.svg"))
    raven_svg = sanitize_inline_svg(_read_asset_text("viarah-raven.svg"))

    title = html.escape(f"Report — {report_run.project.name}")
    template_name = html.escape(str(report_run.template.name or "Report").strip())
    org_name = html.escape(str(report_run.org.name or "Org").strip())
    content_html = render_report_markdown_to_pdf_html(report_run.output_markdown)

    css = """
@page {
  size: A4;
  margin: 18mm 16mm 18mm 16mm;
}

html,
body {
  padding: 0;
  margin: 0;
}

body {
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial,
    sans-serif;
  color: #111827;
}

img,
svg {
  max-width: 100%;
}

h1,
h2,
h3,
h4,
h5,
h6 {
  break-after: avoid-page;
}

pre,
blockquote,
table {
  break-inside: avoid;
}

a {
  color: inherit;
  text-decoration: none;
}

.vr-masthead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 0 10px 0;
  border-bottom: 1px solid #e5e7eb;
  margin: 0 0 16px 0;
}

.vr-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.vr-brand .vr-logo {
  height: 18px;
  width: auto;
  display: block;
}

.vr-brand .vr-org {
  font-size: 10px;
  color: #6b7280;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.vr-title {
  text-align: right;
  min-width: 0;
}

.vr-title .vr-template {
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.vr-title .vr-project {
  font-size: 10px;
  color: #6b7280;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.vr-raven {
  height: 18px;
  width: auto;
  display: block;
}

.vr-content {
  font-size: 12px;
  line-height: 1.45;
}

.vr-content ul {
  padding-left: 18px;
}

.vr-content code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono,
    monospace;
  font-size: 0.95em;
}

.vr-content pre {
  background: #f3f4f6;
  padding: 10px;
  border-radius: 8px;
  overflow: hidden;
}
""".strip()

    return (
        "<!doctype html>"
        "<html>"
        "<head>"
        '<meta charset="utf-8">'
        f"<title>{title}</title>"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<style>{css}</style>"
        "</head>"
        "<body>"
        '<header class="vr-masthead">'
        '<div class="vr-brand">'
        f'<div class="vr-logo" aria-label="Via Logos logo">{vialogos_logo_svg}</div>'
        f'<div class="vr-org">{org_name}</div>'
        "</div>"
        '<div class="vr-title">'
        f'<div class="vr-template">{template_name}</div>'
        f'<div class="vr-project">{html.escape(report_run.project.name)}</div>'
        "</div>"
        f'<div class="vr-raven" aria-label="ViaRah raven icon">{raven_svg}</div>'
        "</header>"
        f'<main class="vr-content">{content_html}</main>'
        "</body>"
        "</html>"
    )


def sanitize_url_for_log(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""

    parts = urlsplit(raw)
    cleaned = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return cleaned[:2000]


def sanitize_error_message(message: str) -> str:
    raw = str(message or "")

    def _replace_url(match: re.Match[str]) -> str:
        return sanitize_url_for_log(match.group(0))

    cleaned = _URL_RE.sub(_replace_url, raw)
    cleaned = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+\b", "Bearer [REDACTED]", cleaned)
    cleaned = re.sub(r"(?i)^\s*authorization\s*:\s*.+$", "Authorization: [REDACTED]", cleaned)
    return cleaned.strip()[:2000]


def _key_is_sensitive(key: object) -> bool:
    lowered = str(key or "").lower()
    return any(sub in lowered for sub in _SENSITIVE_KEY_SUBSTRINGS)


def _sanitize_json_value(value: Any, *, depth: int) -> Any:
    if depth <= 0:
        return None

    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for k, v in value.items():
            if _key_is_sensitive(k):
                continue
            cleaned[str(k)] = _sanitize_json_value(v, depth=depth - 1)
        return cleaned

    if isinstance(value, list):
        return [_sanitize_json_value(v, depth=depth - 1) for v in value[:200]]

    if isinstance(value, str):
        return sanitize_error_message(value)

    if isinstance(value, (int, float, bool)) or value is None:
        return value

    return sanitize_error_message(str(value))


def sanitize_render_qa_report(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return _sanitize_json_value(raw, depth=6) or {}
