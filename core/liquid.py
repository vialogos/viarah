from __future__ import annotations

from liquid import Environment

ALLOWED_LIQUID_FILTERS = {
    "append",
    "capitalize",
    "default",
    "downcase",
    "escape",
    "join",
    "prepend",
    "remove",
    "replace",
    "replace_first",
    "size",
    "slice",
    "sort",
    "split",
    "strip",
    "upcase",
}

_LIQUID_ENV = Environment()
for _filter_name in list(_LIQUID_ENV.filters.keys()):
    if _filter_name not in ALLOWED_LIQUID_FILTERS:
        del _LIQUID_ENV.filters[_filter_name]


class LiquidTemplateError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def validate_liquid_template(body: str) -> None:
    try:
        _LIQUID_ENV.from_string(body or "")
    except Exception as exc:  # noqa: BLE001
        raise LiquidTemplateError("body must be valid Liquid") from exc


def liquid_environment() -> Environment:
    return _LIQUID_ENV
