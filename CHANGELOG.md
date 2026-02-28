# Changelog

## Unreleased

- (none)

## v0.1.0-rc2 - 2026-02-28

- Fixed: `/api/me` (`identity__me_get`) no longer returns `403` for valid API keys when the key owner
  has no `OrgMembership` for the API key’s `org_id` (returns `memberships: []` instead).
- Changed: Platform admin/pm can list all orgs and manage org memberships without pre-seeded `OrgMembership` rows.
- Added: Work item time estimates (`estimate_minutes`) for tasks/subtasks, surfaced in the API and Work detail UI.
- Changed: Invites support explicit delivery mode (`delivery=link|email`); link mode never attempts email (responses include `full_invite_url` + `email_sent`).
- Fixed: Work detail assignee rendering no longer shows an empty “Select a value” state when a value is selected.
- Added: Workflow reassignment tooling (`manage.py migrate_project_workflow`) to safely migrate/clear workflow stage assignments without orphaning work.
- Changed: Branding updates (Via Logos favicon/masthead + subtle footer logo link).
- Changed: Local dev can run parallel stacks by overriding Compose `WEB_PORT` and Vite proxy `VITE_BACKEND_URL`.

## v0.1.0-rc1 - 2026-02-26

- Added: Initial release candidate for ViaRah (Django backend, Vue frontend, docs, and operator workflows).
- Added: Docker Compose-based local stack and GitLab CI (ruff + Django tests).
- Added: Frontend UI built on PatternFly Vue.
