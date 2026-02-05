# share_links

Share links provide a public, token-based URL for viewing a report run’s rendered HTML output. The
raw token is only returned at creation time; the server stores a hash.

## Key entrypoints

- `share_links/models.py` — `ShareLink`, `ShareLinkAccessLog`
- `share_links/services.py` — token minting + HTML build + access logging
- `share_links/views.py`, `share_links/urls.py` — authenticated API endpoints
- `share_links/public_urls.py`, `share_links/public_views.py` — public view endpoint (no auth)

## Models

- `ShareLink` — token-hash link to a `reports.ReportRun` (XOR: created by user vs API key)
- `ShareLinkAccessLog` — IP/user-agent access rows for auditing/analytics

## API routes

Mounted under `/api/`:

- `/api/orgs/<org_id>/report-runs/<report_run_id>/publish` → `share_links.views.publish_share_link_view`
- `/api/orgs/<org_id>/share-links` → `share_links.views.share_links_collection_view`
- `/api/orgs/<org_id>/share-links/<share_link_id>/revoke` → `share_links.views.revoke_share_link_view`
- `/api/orgs/<org_id>/share-links/<share_link_id>/access-logs` → `share_links.views.share_link_access_logs_view`

Public (non-API) route:

- `/p/r/<token>` → `share_links.public_views.public_share_link_view`

The canonical contract is `docs/api/openapi.yaml` + `docs/api/scope-map.yaml`.

## Token + expiry behavior

- Tokens are created via `share_links.services.new_token()` and stored hashed via `hash_token()`.
- Default expiry is 7 days (`default_expires_at()`), but callers can supply an explicit `expires_at`.
- Public resolution (`resolve_active_share_link()`) requires: not revoked, not expired, hash match.

## Interactions / dependencies

- Builds a public report context via `reports.services.build_public_report_context()` and renders the
  output with `render_report_markdown()`.
- Sanitizes output using `collaboration.services.render_markdown_to_safe_html()`.
- Emits `report.published` via `notifications.services.emit_report_published()` at creation time.
- Writes audit events via `audit.services.write_audit_event`.
