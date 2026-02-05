from __future__ import annotations

import hashlib
import re

import bleach
from markdown_it import MarkdownIt

_LINK_REL = "nofollow noopener noreferrer"

_MD = MarkdownIt("commonmark", {"html": False})
_MD.disable("image")

_ALLOWED_TAGS = [
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
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "ul",
]

_ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
}

_ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

_A_OPEN_RE = re.compile(r"<a(?P<attrs>\s+[^>]*?)?>", re.IGNORECASE)
_REL_PRESENT_RE = re.compile(r"\srel\s*=", re.IGNORECASE)


def _ensure_link_rel(html: str) -> str:
    def _replace(match: re.Match) -> str:
        attrs = match.group("attrs") or ""
        if _REL_PRESENT_RE.search(attrs):
            return f"<a{attrs}>"
        attrs_str = attrs.strip()
        if not attrs_str:
            return f'<a rel="{_LINK_REL}">'
        return f'<a {attrs_str} rel="{_LINK_REL}">'

    return _A_OPEN_RE.sub(_replace, html)


def render_markdown_to_safe_html(body_markdown: str) -> str:
    """Render markdown to sanitized HTML suitable for untrusted user input.

    Uses CommonMark parsing with HTML and images disabled, then applies an allowlist via `bleach`.
    Link tags are normalized to include a safe `rel` attribute.
    """
    raw_html = _MD.render(body_markdown or "")
    cleaned = bleach.clean(
        raw_html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )
    return _ensure_link_rel(cleaned).strip()


def compute_sha256(uploaded_file) -> str:
    """Compute SHA-256 for an uploaded file without consuming it permanently.

    Reads via Django's `chunks()` and rewinds the file when possible.
    """
    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    if hasattr(uploaded_file, "seek"):
        try:
            uploaded_file.seek(0)
        except (OSError, ValueError):
            pass
    return digest.hexdigest()
