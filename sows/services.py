from __future__ import annotations

import hashlib

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from audit.services import write_audit_event
from collaboration.services import render_markdown_to_safe_html
from core.liquid import liquid_environment
from templates.models import TemplateType

from .models import SoW, SoWSigner, SoWVersion

MAX_RENDERED_MARKDOWN_CHARS = 200_000
MAX_RENDERED_HTML_CHARS = 400_000

_LIQUID_ENV = liquid_environment()


class SoWValidationError(Exception):
    """Raised when SoW inputs/state transitions are invalid or unsafe."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def build_sow_context(*, org, project, variables: dict) -> dict:
    """Build the SoW Liquid render context for a project and variable set."""
    return {
        "org": {"id": str(org.id), "name": org.name},
        "project": {
            "id": str(project.id),
            "name": project.name,
            "description": project.description,
        },
        "variables": variables,
    }


def render_sow_markdown(*, template_body: str, context: dict) -> str:
    """Render the SoW Liquid template to markdown and enforce size limits."""
    try:
        liquid_template = _LIQUID_ENV.from_string(template_body or "")
        rendered = liquid_template.render(**context)
    except Exception as exc:  # noqa: BLE001
        raise SoWValidationError("failed to render Liquid template") from exc

    if len(rendered) > MAX_RENDERED_MARKDOWN_CHARS:
        raise SoWValidationError("rendered output is too large")

    return rendered.strip()


def render_sow_html(*, body_markdown: str) -> str:
    """Render SoW markdown to sanitized HTML and enforce size limits."""
    html = render_markdown_to_safe_html(body_markdown)
    if len(html) > MAX_RENDERED_HTML_CHARS:
        raise SoWValidationError("rendered output is too large")
    return html


def compute_content_sha256(*, body_markdown: str) -> str:
    """Compute a stable SHA-256 hash for signed SoW content (markdown)."""
    return hashlib.sha256((body_markdown or "").encode("utf-8")).hexdigest()


def _require_template_is_sow(template) -> None:
    if template.type != TemplateType.SOW:
        raise SoWValidationError("template must be a sow template")


def _next_version_number(*, sow: SoW) -> int:
    max_version = SoWVersion.objects.filter(sow=sow).aggregate(m=Max("version"))["m"] or 0
    return int(max_version) + 1


def create_sow(
    *,
    org,
    project,
    template,
    template_version,
    variables: dict,
    signer_users: list,
    created_by_user,
) -> tuple[SoW, SoWVersion]:
    """Create a new SoW and initial draft version with signers.

    Side effects: Persists `SoW`, `SoWVersion`, and signer rows and writes an audit event.
    """
    _require_template_is_sow(template)

    if not signer_users:
        raise SoWValidationError("signer_user_ids is required")

    context = build_sow_context(org=org, project=project, variables=variables)
    body_markdown = render_sow_markdown(template_body=template_version.body, context=context)
    body_html = render_sow_html(body_markdown=body_markdown)

    with transaction.atomic():
        sow = SoW.objects.create(
            org=org,
            project=project,
            template=template,
            created_by_user=created_by_user,
        )
        version = SoWVersion.objects.create(
            sow=sow,
            version=1,
            template_version=template_version,
            variables_json=variables,
            body_markdown=body_markdown,
            body_html=body_html,
            content_sha256="",
            locked_at=None,
            status=SoWVersion.Status.DRAFT,
            created_by_user=created_by_user,
        )

        SoWSigner.objects.bulk_create(
            [
                SoWSigner(
                    sow_version=version,
                    signer_user=user,
                    status=SoWSigner.Status.PENDING,
                    decision_comment="",
                    typed_signature="",
                    responded_at=None,
                )
                for user in signer_users
            ]
        )

        sow.current_version = version
        sow.save(update_fields=["current_version", "updated_at"])

        write_audit_event(
            org=org,
            actor_user=created_by_user,
            event_type="sow.created",
            metadata={
                "sow_id": str(sow.id),
                "sow_version_id": str(version.id),
                "project_id": str(project.id),
                "content_hash": "",
            },
        )

    return sow, version


def create_sow_version(
    *,
    sow: SoW,
    template_version,
    variables: dict,
    signer_users: list,
    created_by_user,
) -> SoWVersion:
    """Create a new draft SoW version and set it as current.

    Invariants: blocked while the current version is pending signature; resets signers for the new
    version.
    """
    _require_template_is_sow(sow.template)

    if not signer_users:
        raise SoWValidationError("signer_user_ids is required")

    context = build_sow_context(org=sow.org, project=sow.project, variables=variables)
    body_markdown = render_sow_markdown(template_body=template_version.body, context=context)
    body_html = render_sow_html(body_markdown=body_markdown)

    with transaction.atomic():
        locked_sow = (
            SoW.objects.select_for_update()
            .select_related("org", "project", "template")
            .get(id=sow.id)
        )
        if locked_sow.current_version_id:
            current = (
                SoWVersion.objects.select_for_update()
                .filter(id=locked_sow.current_version_id, sow=locked_sow)
                .first()
            )
            if current is not None and current.status == SoWVersion.Status.PENDING_SIGNATURE:
                raise SoWValidationError("cannot create a new version while signature is pending")

        version_number = _next_version_number(sow=locked_sow)
        version = SoWVersion.objects.create(
            sow=locked_sow,
            version=version_number,
            template_version=template_version,
            variables_json=variables,
            body_markdown=body_markdown,
            body_html=body_html,
            content_sha256="",
            locked_at=None,
            status=SoWVersion.Status.DRAFT,
            created_by_user=created_by_user,
        )

        SoWSigner.objects.bulk_create(
            [
                SoWSigner(
                    sow_version=version,
                    signer_user=user,
                    status=SoWSigner.Status.PENDING,
                    decision_comment="",
                    typed_signature="",
                    responded_at=None,
                )
                for user in signer_users
            ]
        )

        locked_sow.current_version = version
        locked_sow.save(update_fields=["current_version", "updated_at"])

    return version


def send_sow(*, sow: SoW, actor_user) -> SoWVersion:
    """Transition the current SoW version from DRAFT to PENDING_SIGNATURE.

    Invariants: requires at least one signer. Stores a content hash used for signing/audit trails.
    Side effects: Updates the version state and writes an audit event.
    """
    if sow.current_version_id is None:
        raise SoWValidationError("sow has no current version")

    with transaction.atomic():
        locked_sow = SoW.objects.select_for_update().get(id=sow.id)
        version = (
            SoWVersion.objects.select_for_update()
            .select_related("sow__org")
            .filter(id=locked_sow.current_version_id, sow=locked_sow)
            .first()
        )
        if version is None:
            raise SoWValidationError("sow has no current version")
        if version.status != SoWVersion.Status.DRAFT:
            raise SoWValidationError("sow is not in a draft state")

        signer_count = SoWSigner.objects.filter(sow_version=version).count()
        if signer_count < 1:
            raise SoWValidationError("sow must have at least one signer")

        content_hash = compute_content_sha256(body_markdown=version.body_markdown)
        version.status = SoWVersion.Status.PENDING_SIGNATURE
        version.locked_at = timezone.now()
        version.content_sha256 = content_hash
        version.save(update_fields=["status", "locked_at", "content_sha256"])

        write_audit_event(
            org=version.sow.org,
            actor_user=actor_user,
            event_type="sow.sent",
            metadata={
                "sow_id": str(version.sow_id),
                "sow_version_id": str(version.id),
                "project_id": str(version.sow.project_id),
                "content_hash": content_hash,
            },
        )

    return version


def signer_respond(
    *,
    sow: SoW,
    signer_user,
    decision: str,
    comment: str,
    typed_signature: str,
) -> SoWVersion:
    """Record a signer decision and advance SoW status when appropriate.

    Invariants:
    - Only signers on the current version can respond.
    - Approvals require a typed signature; any rejection rejects the version immediately.
    Side effects: Updates signer and version status and writes audit events.
    """
    if sow.current_version_id is None:
        raise SoWValidationError("sow has no current version")

    decision_normalized = str(decision or "").strip().lower()
    if decision_normalized not in {"approve", "reject"}:
        raise SoWValidationError("decision must be approve or reject")

    comment_value = str(comment or "").strip()
    typed_signature_value = str(typed_signature or "").strip()
    if decision_normalized == "approve" and not typed_signature_value:
        raise SoWValidationError("typed_signature is required when approving")

    with transaction.atomic():
        locked_sow = SoW.objects.select_for_update().get(id=sow.id)
        version = (
            SoWVersion.objects.select_for_update()
            .select_related("sow__org")
            .filter(id=locked_sow.current_version_id, sow=locked_sow)
            .first()
        )
        if version is None:
            raise SoWValidationError("sow has no current version")
        if version.status != SoWVersion.Status.PENDING_SIGNATURE:
            raise SoWValidationError("sow is not pending signature")

        signer = (
            SoWSigner.objects.select_for_update()
            .filter(sow_version=version, signer_user=signer_user)
            .first()
        )
        if signer is None:
            raise SoWValidationError("forbidden")
        if signer.status != SoWSigner.Status.PENDING:
            raise SoWValidationError("signer has already responded")

        now = timezone.now()
        if decision_normalized == "reject":
            signer.status = SoWSigner.Status.REJECTED
        else:
            signer.status = SoWSigner.Status.APPROVED
        signer.decision_comment = comment_value
        signer.typed_signature = typed_signature_value if decision_normalized == "approve" else ""
        signer.responded_at = now
        signer.save(update_fields=["status", "decision_comment", "typed_signature", "responded_at"])

        content_hash = str(version.content_sha256 or "").strip()

        write_audit_event(
            org=version.sow.org,
            actor_user=signer_user,
            event_type=(
                "sow.signer_rejected" if decision_normalized == "reject" else "sow.signer_approved"
            ),
            metadata={
                "sow_id": str(version.sow_id),
                "sow_version_id": str(version.id),
                "project_id": str(version.sow.project_id),
                "content_hash": content_hash,
            },
        )

        if decision_normalized == "reject":
            version.status = SoWVersion.Status.REJECTED
            version.save(update_fields=["status"])
            write_audit_event(
                org=version.sow.org,
                actor_user=signer_user,
                event_type="sow.rejected",
                metadata={
                    "sow_id": str(version.sow_id),
                    "sow_version_id": str(version.id),
                    "project_id": str(version.sow.project_id),
                    "content_hash": content_hash,
                },
            )
            return version

        all_approved = not SoWSigner.objects.filter(
            sow_version=version, status=SoWSigner.Status.PENDING
        ).exists()
        if all_approved:
            version.status = SoWVersion.Status.SIGNED
            version.save(update_fields=["status"])
            write_audit_event(
                org=version.sow.org,
                actor_user=signer_user,
                event_type="sow.signed",
                metadata={
                    "sow_id": str(version.sow_id),
                    "sow_version_id": str(version.id),
                    "project_id": str(version.sow.project_id),
                    "content_hash": content_hash,
                },
            )

    return version
