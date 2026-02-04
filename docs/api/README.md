# ViaRah API docs (API completeness v1)

This folder contains the source-of-truth API contract artifacts for ViaRah.

## Artifacts
- `openapi.yaml`: OpenAPI 3.x spec for all `/api/...` endpoints.
- `scope-map.yaml`: Explicit per-operation authorization map (session vs API key vs webhook).
- `auth.md`: API-key token format and `/api/me` semantics.

## Local validation

### Run completeness checks (recommended)
Run from the repo root:
```bash
python -m pip install -r requirements-dev.txt
python scripts/api_completeness_check.py
```

The completeness check enforces:
- Every Django `/api/...` route+method is present in `openapi.yaml`.
- Every OpenAPI operation has an entry in `scope-map.yaml`.
- `openapi.yaml` is OpenAPI-valid (library validator).

### Full smoke (Docker Compose)
The repo’s `README.md` contains the canonical Docker Compose smoke commands.

## Maintenance expectations
- If you add or change an `/api/...` endpoint, update `openapi.yaml` and `scope-map.yaml` in the same MR.
- Keep `scope-map.yaml` client-safe; it should describe auth gates, not leak data.

