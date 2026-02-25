# integrations

Integrations currently focuses on GitLab:

- per-org GitLab configuration (base URL, encrypted token, webhook secret hash)
- linking tasks to GitLab issues/MRs (“live links”)
- webhook ingestion for issue/MR updates and background metadata refresh

## Key entrypoints

- `integrations/models.py` — `OrgGitLabIntegration`, `TaskGitLabLink`, `GitLabWebhookDelivery`
- `integrations/services.py` — origin normalization, URL parsing, token encryption, webhook secret hashing
- `integrations/gitlab.py` — `GitLabClient` HTTP wrapper
- `integrations/tasks.py` — metadata refresh + webhook delivery processing (Celery tasks)
- `integrations/views.py`, `integrations/urls.py` — REST API + webhook endpoint

## Models

- `OrgGitLabIntegration` — org-scoped config: `base_url`, `token_ciphertext`, `webhook_secret_hash`
- `TaskGitLabLink` — link from `work_items.Task` → GitLab issue/MR (`project_path`, `gitlab_iid`)
- `GitLabWebhookDelivery` — stored webhook events for async processing and auditing

## API routes

Mounted under `/api/`:

- `/api/orgs/<org_id>/integrations/gitlab` → `integrations.views.org_gitlab_integration_view`
- `/api/orgs/<org_id>/integrations/gitlab/validate` → `integrations.views.gitlab_integration_validate_view`
- `/api/orgs/<org_id>/tasks/<task_id>/gitlab-links` → `integrations.views.task_gitlab_links_collection_view`
- `/api/orgs/<org_id>/tasks/<task_id>/gitlab-links/<link_id>` → `integrations.views.task_gitlab_link_delete_view`
- `/api/orgs/<org_id>/integrations/gitlab/webhook` → `integrations.views.gitlab_webhook_view` (token-verified)

The canonical contract is `docs/api/openapi.yaml` + `docs/api/scope-map.yaml`.

## Security / configuration

- Tokens are encrypted at rest using `VIA_RAH_ENCRYPTION_KEY` (Fernet) via
  `integrations.services.encrypt_token()` / `decrypt_token()`.
- The webhook endpoint uses the `X-Gitlab-Token` header and a stored hash
  (`integrations.services.webhook_secret_matches()`).
- Optional metadata refresh tuning: `GITLAB_METADATA_TTL_SECONDS` (see `.env.example`).

## Background jobs / tasks

- `integrations.tasks.refresh_gitlab_link_metadata()` fetches issue/MR title/state/labels/assignees
  and caches them on `TaskGitLabLink`.
- `integrations.tasks.process_gitlab_webhook_delivery()` finds matching `TaskGitLabLink` rows and
  enqueues refresh for each.

## Interactions / dependencies

- Links attach to `work_items.Task` and are access-controlled via org membership checks in
  `integrations/views.py`.
- Writes audit events for configuration changes via `audit.services.write_audit_event`.
