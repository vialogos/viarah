from __future__ import annotations

from django.db import transaction
from django.db.models import Max

from core.liquid import LiquidTemplateError, validate_liquid_template

from .models import Template, TemplateType, TemplateVersion

MAX_TEMPLATE_BODY_CHARS = 20_000

class TemplateValidationError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _validate_template_type(template_type: str) -> str:
    template_type_normalized = str(template_type or "").strip()
    if template_type_normalized not in set(TemplateType.values):
        raise TemplateValidationError("type must be one of: report, email, comment, sow")
    return template_type_normalized


def validate_template_body(body: str) -> str:
    if body is None:
        raise TemplateValidationError("body is required")
    if not isinstance(body, str):
        raise TemplateValidationError("body must be a string")
    body_str = body
    if not body_str.strip():
        raise TemplateValidationError("body is required")
    if len(body_str) > MAX_TEMPLATE_BODY_CHARS:
        raise TemplateValidationError("body is too long")
    try:
        validate_liquid_template(body_str)
    except LiquidTemplateError as exc:
        raise TemplateValidationError(exc.message) from exc
    return body_str


def create_template(
    *,
    org,
    template_type: object,
    name: object,
    description: object,
    body: object,
    created_by_user,
) -> tuple[Template, TemplateVersion]:
    template_type_value = _validate_template_type(str(template_type or ""))
    name_value = str(name or "").strip()
    if not name_value:
        raise TemplateValidationError("name is required")
    description_value = str(description or "").strip() if description is not None else ""
    body_value = validate_template_body(body)

    with transaction.atomic():
        template = Template.objects.create(
            org=org,
            type=template_type_value,
            name=name_value,
            description=description_value,
            created_by_user=created_by_user,
        )
        version = TemplateVersion.objects.create(
            template=template, version=1, body=body_value, created_by_user=created_by_user
        )
        template.current_version = version
        template.save(update_fields=["current_version", "updated_at"])

    return template, version


def create_template_version(
    *, template: Template, body: object, created_by_user
) -> TemplateVersion:
    body_value = validate_template_body(body)

    with transaction.atomic():
        locked_template = Template.objects.select_for_update().get(id=template.id)
        max_version = (
            TemplateVersion.objects.filter(template=locked_template).aggregate(m=Max("version"))[
                "m"
            ]
            or 0
        )
        version = TemplateVersion.objects.create(
            template=locked_template,
            version=int(max_version) + 1,
            body=body_value,
            created_by_user=created_by_user,
        )
        locked_template.current_version = version
        locked_template.save(update_fields=["current_version", "updated_at"])

    return version
