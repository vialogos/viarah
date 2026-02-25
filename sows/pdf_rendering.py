from __future__ import annotations

import html
from pathlib import Path

from django.conf import settings

from reports.pdf_rendering import render_report_markdown_to_pdf_html, sanitize_inline_svg

from .models import SoWSigner, SoWVersion


def _assets_dir() -> Path:
    return Path(settings.BASE_DIR) / "reports" / "pdf_assets"


def _read_asset_text(filename: str) -> str:
    path = _assets_dir() / filename
    return path.read_text(encoding="utf-8")


def build_sow_pdf_html(*, sow_version: SoWVersion, signers: list[SoWSigner]) -> str:
    vialogos_logo_svg = sanitize_inline_svg(_read_asset_text("via-logos-logo.svg"))
    raven_svg = sanitize_inline_svg(_read_asset_text("viarah-raven.svg"))

    sow = sow_version.sow
    project = sow.project
    org = sow.org

    title = html.escape(f"Statement of Work — {project.name}")
    content_html = render_report_markdown_to_pdf_html(sow_version.body_markdown)

    signer_lines = []
    for signer in signers:
        status = html.escape(str(signer.status))
        email = html.escape(str(getattr(signer.signer_user, "email", "") or "").strip())
        responded = signer.responded_at.isoformat() if signer.responded_at else ""
        responded_esc = html.escape(responded)
        sig = html.escape(str(signer.typed_signature or "").strip())
        if signer.status == SoWSigner.Status.APPROVED:
            signer_lines.append(
                f"<li><strong>{email}</strong> — {status}"
                f"{' — ' + responded_esc if responded else ''}"
                f"{'<br><em>' + sig + '</em>' if sig else ''}</li>"
            )
        else:
            signer_lines.append(
                f"<li><strong>{email}</strong> — {status}"
                f"{' — ' + responded_esc if responded else ''}</li>"
            )

    signers_html = "<ul>" + "".join(signer_lines) + "</ul>" if signer_lines else "<p>None</p>"

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

.vr-meta {
  margin: 0 0 16px 0;
  font-size: 10px;
  color: #6b7280;
}

.vr-signers {
  margin: 0 0 18px 0;
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.vr-signers h2 {
  margin: 0 0 8px 0;
  font-size: 12px;
  color: #111827;
}

.vr-content {
  font-size: 11px;
  line-height: 1.45;
}
"""

    org_name = html.escape(str(org.name or "Org").strip())
    project_name = html.escape(str(project.name or "Project").strip())
    version_num = int(sow_version.version)
    locked_at = sow_version.locked_at.isoformat() if sow_version.locked_at else ""
    content_hash = html.escape(str(sow_version.content_sha256 or "").strip())

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
        '<div class="vr-masthead">'
        '<div class="vr-brand">'
        f'<div class="vr-logo">{vialogos_logo_svg}</div>'
        f'<div class="vr-org">{org_name}</div>'
        "</div>"
        '<div class="vr-title">'
        '<div class="vr-template">Statement of Work</div>'
        f'<div class="vr-project">{project_name}</div>'
        "</div>"
        f'<div class="vr-raven">{raven_svg}</div>'
        "</div>"
        f'<div class="vr-meta">Version v{version_num}'
        f"{' • Locked ' + html.escape(locked_at) if locked_at else ''}"
        f"{' • Hash ' + content_hash if content_hash else ''}"
        "</div>"
        '<div class="vr-signers">'
        "<h2>Signers</h2>"
        f"{signers_html}"
        "</div>"
        f'<div class="vr-content">{content_html}</div>'
        "</body>"
        "</html>"
    )
