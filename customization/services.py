from __future__ import annotations

import datetime
import re

from work_items.models import WorkItemStatus

_ISO_DATE_RE = re.compile(r"^\\d{4}-\\d{2}-\\d{2}$")


def normalize_saved_view_filters(value: object) -> dict:
    """Normalize saved-view filter payloads.

    Expected shape: `{status: [<WorkItemStatus>...], search: <string>}`.
    Missing/None yields a stable default with empty status list and empty search string.
    """
    if value is None:
        return {"status": [], "search": ""}
    if not isinstance(value, dict):
        raise ValueError("filters must be an object")

    allowed_keys = {"status", "search"}
    unknown = set(value.keys()) - allowed_keys
    if unknown:
        raise ValueError(f"filters contains unsupported keys: {sorted(unknown)}")

    raw_status = value.get("status", [])
    if raw_status is None:
        raw_status = []
    if not isinstance(raw_status, list):
        raise ValueError("filters.status must be a list")
    statuses: list[str] = []
    for item in raw_status:
        if not isinstance(item, str):
            raise ValueError("filters.status entries must be strings")
        status = item.strip()
        if status not in set(WorkItemStatus.values):
            raise ValueError("filters.status contains invalid status")
        statuses.append(status)

    raw_search = value.get("search", "")
    if raw_search is None:
        raw_search = ""
    if not isinstance(raw_search, str):
        raise ValueError("filters.search must be a string")

    return {"status": statuses, "search": raw_search}


def normalize_saved_view_sort(value: object) -> dict:
    """Normalize saved-view sort payloads.

    Expected shape: `{field, direction}`; defaults to `{field: created_at, direction: asc}`.
    """
    if value is None:
        return {"field": "created_at", "direction": "asc"}
    if not isinstance(value, dict):
        raise ValueError("sort must be an object")

    allowed_keys = {"field", "direction"}
    unknown = set(value.keys()) - allowed_keys
    if unknown:
        raise ValueError(f"sort contains unsupported keys: {sorted(unknown)}")

    field = value.get("field", "created_at")
    if not isinstance(field, str) or not field.strip():
        raise ValueError("sort.field must be a string")
    field = field.strip()
    if field not in {"created_at", "updated_at", "title"}:
        raise ValueError("sort.field is invalid")

    direction = value.get("direction", "asc")
    if not isinstance(direction, str) or not direction.strip():
        raise ValueError("sort.direction must be a string")
    direction = direction.strip()
    if direction not in {"asc", "desc"}:
        raise ValueError("sort.direction is invalid")

    return {"field": field, "direction": direction}


def normalize_saved_view_group_by(value: object) -> str:
    """Normalize saved-view group_by values (`none` or `status`)."""
    if value is None:
        return "none"
    if not isinstance(value, str):
        raise ValueError("group_by must be a string")
    group_by = value.strip()
    if group_by not in {"none", "status"}:
        raise ValueError("group_by is invalid")
    return group_by


def normalize_custom_field_options(field_type: str, value: object) -> list[str]:
    """Normalize and validate a custom field's options list for the given field type."""
    if value is None:
        options: list[str] = []
    else:
        if not isinstance(value, list):
            raise ValueError("options must be a list")
        options = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("options entries must be strings")
            option = item.strip()
            if not option:
                raise ValueError("options entries must be non-empty strings")
            options.append(option)

    if field_type in {"select", "multi_select"}:
        if not options:
            raise ValueError("options is required for select fields")
        if len(set(options)) != len(options):
            raise ValueError("options entries must be unique")
        return options

    if options:
        raise ValueError("options must be empty for non-select fields")
    return []


def validate_custom_field_value(field_type: str, options: list[str], value: object) -> object:
    """Validate and normalize a custom field value against its type and options."""
    if field_type == "text":
        if not isinstance(value, str):
            raise ValueError("value must be a string")
        return value

    if field_type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("value must be a number")
        return value

    if field_type == "date":
        if not isinstance(value, str):
            raise ValueError("value must be a YYYY-MM-DD string")
        if not _ISO_DATE_RE.match(value):
            raise ValueError("value must be a YYYY-MM-DD string")
        try:
            datetime.date.fromisoformat(value)
        except ValueError:
            raise ValueError("value must be a valid YYYY-MM-DD date") from None
        return value

    if field_type == "select":
        if not isinstance(value, str):
            raise ValueError("value must be a string")
        if value not in set(options):
            raise ValueError("value must be one of the field options")
        return value

    if field_type == "multi_select":
        if not isinstance(value, list):
            raise ValueError("value must be a list")
        values: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("value entries must be strings")
            if item not in set(options):
                raise ValueError("value entries must be one of the field options")
            values.append(item)
        if len(set(values)) != len(values):
            raise ValueError("value entries must be unique")
        return values

    raise ValueError("invalid field_type")
