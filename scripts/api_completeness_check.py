#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

_DJANGO_PARAM_RE = re.compile(r"<(?:(?P<converter>[^:>]+):)?(?P<name>[^>]+)>")
_HTTP_METHODS = {"GET", "POST", "PATCH", "DELETE"}


@dataclass(frozen=True, slots=True)
class ApiRoute:
    method: str
    path: str


def _load_yaml(path: Path) -> Any:
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError(
            "PyYAML is required. Install dev deps: python -m pip install -r requirements-dev.txt"
        ) from exc

    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(f"missing required file: {path}") from exc

    data = yaml.safe_load(raw)
    if data is None:
        raise RuntimeError(f"YAML file is empty: {path}")
    return data


def _validate_openapi(spec: dict[str, Any]) -> None:
    try:
        from openapi_spec_validator import validate_spec  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError(
            "openapi-spec-validator is required. Install dev deps: "
            "python -m pip install -r requirements-dev.txt"
        ) from exc

    validate_spec(spec)


def _django_route_to_openapi_path(route: str) -> str:
    route = route.lstrip("/")
    route = _DJANGO_PARAM_RE.sub(lambda m: "{" + m.group("name") + "}", route)
    return "/" + route


def _extract_request_method_list(func) -> list[str] | None:
    closure = getattr(func, "__closure__", None)
    code = getattr(func, "__code__", None)
    if not closure or not code:
        return None

    freevars = getattr(code, "co_freevars", None)
    if not freevars:
        return None

    # django.views.decorators.http.require_http_methods stores the allowed list in a closure
    # variable named "request_method_list".
    freevar_cells = dict(zip(freevars, closure, strict=False))
    cell = freevar_cells.get("request_method_list")
    if cell is None:
        return None

    try:
        value = cell.cell_contents
    except ValueError:
        return None

    if not isinstance(value, (list, tuple, set)):
        return None

    methods = [str(m).upper() for m in value if str(m).strip()]
    return methods or None


def _unwrap_for_allowed_methods(callback) -> list[str] | None:
    current = callback
    seen: set[int] = set()
    while current is not None:
        methods = _extract_request_method_list(current)
        if methods:
            return methods
        current_id = id(current)
        if current_id in seen:
            break
        seen.add(current_id)
        current = getattr(current, "__wrapped__", None)
    return None


def _pattern_route(pattern) -> str:
    route = getattr(pattern, "_route", None)
    if isinstance(route, str):
        return route
    # Best-effort fallback for regex patterns; these are currently not used in ViaRah routes.
    regex = getattr(getattr(pattern, "regex", None), "pattern", None)
    if isinstance(regex, str):
        return regex
    return str(pattern)


def _iter_django_routes() -> set[ApiRoute]:
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root))

    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        str(os.environ.get("DJANGO_SETTINGS_MODULE", "") or "viarah.settings.dev"),
    )

    import django
    from django.urls import URLPattern, URLResolver, get_resolver

    django.setup()

    def _walk(patterns, prefix: str) -> Iterable[tuple[str, object]]:
        for entry in patterns:
            if isinstance(entry, URLPattern):
                yield prefix + _pattern_route(entry.pattern), entry.callback
            elif isinstance(entry, URLResolver):
                yield from _walk(entry.url_patterns, prefix + _pattern_route(entry.pattern))

    routes: set[ApiRoute] = set()
    for django_route, callback in _walk(get_resolver().url_patterns, prefix=""):
        django_route = django_route.lstrip("/")
        if not django_route.startswith("api/"):
            continue

        allowed = _unwrap_for_allowed_methods(callback)
        if not allowed:
            raise RuntimeError(
                f"cannot determine allowed methods for route '"
                f"/{django_route}'. Ensure it is decorated with @require_http_methods([...])."
            )

        openapi_path = _django_route_to_openapi_path(django_route)
        for method in allowed:
            if method in _HTTP_METHODS:
                routes.add(ApiRoute(method=method, path=openapi_path))

    return routes


def _extract_openapi_operations(spec: dict[str, Any]) -> tuple[set[ApiRoute], set[str]]:
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        raise RuntimeError("OpenAPI spec is missing 'paths' object")

    ops: set[ApiRoute] = set()
    op_ids: set[str] = set()

    for raw_path, path_item in paths.items():
        if not isinstance(raw_path, str) or not isinstance(path_item, dict):
            continue
        for raw_method, op in path_item.items():
            method = str(raw_method).upper()
            if method not in _HTTP_METHODS:
                continue
            if not isinstance(op, dict):
                continue
            if "operationId" not in op:
                raise RuntimeError(f"OpenAPI operation is missing operationId: {method} {raw_path}")
            op_id = str(op.get("operationId", "")).strip()
            if not op_id:
                raise RuntimeError(f"OpenAPI operation has empty operationId: {method} {raw_path}")

            if raw_path.startswith("/api/"):
                ops.add(ApiRoute(method=method, path=str(raw_path)))
                op_ids.add(op_id)

    return ops, op_ids


def _load_scope_map_operation_ids(scope_map: dict[str, Any]) -> set[str]:
    ops = scope_map.get("operations")
    if not isinstance(ops, dict):
        raise RuntimeError("scope-map.yaml must have a top-level 'operations' mapping")
    return {str(k).strip() for k in ops.keys() if str(k).strip()}


def _print_routes(title: str, routes: Iterable[ApiRoute]) -> None:
    print(title)
    for r in sorted(routes, key=lambda x: (x.path, x.method)):
        print(f"- {r.method} {r.path}")


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    openapi_path = repo_root / "docs" / "api" / "openapi.yaml"
    scope_map_path = repo_root / "docs" / "api" / "scope-map.yaml"

    openapi_spec = _load_yaml(openapi_path)
    if not isinstance(openapi_spec, dict):
        raise RuntimeError("docs/api/openapi.yaml must parse to a YAML mapping/object")

    scope_map = _load_yaml(scope_map_path)
    if not isinstance(scope_map, dict):
        raise RuntimeError("docs/api/scope-map.yaml must parse to a YAML mapping/object")

    _validate_openapi(openapi_spec)

    django_routes = _iter_django_routes()
    openapi_routes, openapi_op_ids = _extract_openapi_operations(openapi_spec)
    scope_map_op_ids = _load_scope_map_operation_ids(scope_map)

    missing_in_openapi = django_routes - openapi_routes
    extra_in_openapi = openapi_routes - django_routes

    missing_in_scope_map = openapi_op_ids - scope_map_op_ids
    extra_in_scope_map = scope_map_op_ids - openapi_op_ids

    ok = True

    if missing_in_openapi:
        ok = False
        _print_routes(
            "ERROR: routes missing from OpenAPI (docs/api/openapi.yaml):",
            missing_in_openapi,
        )
        print()

    if extra_in_openapi:
        ok = False
        _print_routes(
            "ERROR: OpenAPI has routes not present in Django URL config:", extra_in_openapi
        )
        print()

    if missing_in_scope_map:
        ok = False
        print("ERROR: OpenAPI operations missing from scope-map.yaml:")
        for op_id in sorted(missing_in_scope_map):
            print(f"- {op_id}")
        print()

    if extra_in_scope_map:
        ok = False
        print("ERROR: scope-map.yaml contains unknown operationIds:")
        for op_id in sorted(extra_in_scope_map):
            print(f"- {op_id}")
        print()

    if not ok:
        return 1

    print(
        "OK: API completeness check passed "
        f"({len(django_routes)} routes; "
        f"{len(openapi_op_ids)} operations; "
        f"{len(scope_map_op_ids)} auth-map ops)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
