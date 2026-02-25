# notifications

Notifications track user-facing events, preferences, and delivery logs (in-app, email, and push).

## Key entrypoints

- `notifications/models.py` — core models + enums (`NotificationEventType`, `NotificationChannel`)
- `notifications/services.py` — event emission + preference resolution
- `notifications/tasks.py` — email delivery task
- `notifications/views.py`, `notifications/urls.py` — API endpoints

## Models

- `NotificationEvent` — org/project-scoped event row (`event_type`, `data_json`)
- `InAppNotification` — per-recipient in-app notification row
- `NotificationPreference` — per-user preference per project/event/channel
- `ProjectNotificationSetting` — per-project default/override switch per event/channel
- `EmailDeliveryLog` — queued/success/failure log for outbound email

## API routes

Mounted under `/api/`:

- `/api/orgs/<org_id>/me/notifications` → `notifications.views.my_notifications_collection_view`
- `/api/orgs/<org_id>/me/notifications/badge` → `notifications.views.my_notifications_badge_view`
- `/api/orgs/<org_id>/me/notifications/mark-all-read` → `notifications.views.my_notifications_mark_all_read_view`
- `/api/orgs/<org_id>/me/notifications/<notification_id>` → `notifications.views.my_notification_detail_view`
- `/api/orgs/<org_id>/projects/<project_id>/notification-preferences` → `notifications.views.notification_preferences_view`
- `/api/orgs/<org_id>/projects/<project_id>/notification-settings` → `notifications.views.notification_project_settings_view`
- `/api/orgs/<org_id>/projects/<project_id>/notification-delivery-logs` → `notifications.views.notification_delivery_logs_view`
- `/api/orgs/<org_id>/projects/<project_id>/notification-events` → `notifications.views.project_notification_events_view`

The canonical contract is `docs/api/openapi.yaml` + `docs/api/scope-map.yaml`.

## Auth / access control

Patterns vary by endpoint:

- “My notifications” endpoints require a session user and explicitly forbid API keys (see
  `_require_session_user()` in `notifications/views.py`).
- The project-level event list (`project_notification_events_view`) supports API keys for read-only
  access, with org match and optional `project_id` restriction.

## Background jobs / tasks

- `notifications.tasks.send_email_delivery()` sends queued `EmailDeliveryLog` entries and updates
  status/error fields. It’s enqueued via `notifications.services._enqueue_delivery_log()`.
- Push delivery is triggered via `push.tasks.send_push_for_notification_event()` (enqueued from
  `notifications/services.py` when push is enabled and preferences allow it).

## Interactions / dependencies

- Work item changes call `emit_project_event()` / `emit_assignment_changed()` from `work_items/views.py`.
- Share-link publishing emits `report.published` via `notifications.services.emit_report_published()`
  (called from `share_links/services.py`).
- Outbound email drafts write `EmailDeliveryLog` rows via `outbound_comms/services.py`.
