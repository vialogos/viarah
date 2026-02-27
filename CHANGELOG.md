# Changelog

## Unreleased

- Fixed: `/api/me` (`identity__me_get`) no longer returns `403` for valid API keys when the key owner
  has no `OrgMembership` for the API key’s `org_id` (returns `memberships: []` instead).

## v0.1.0-rc1 - 2026-02-26

- Added: Initial release candidate for ViaRah (Django backend, Vue frontend, docs, and operator workflows).
- Added: Docker Compose-based local stack and GitLab CI (ruff + Django tests).
- Added: Frontend UI built on PatternFly Vue.
