from django.urls import path

from . import views

urlpatterns = [
    path("orgs/<uuid:org_id>/me/notifications", views.my_notifications_collection_view),
    path("orgs/<uuid:org_id>/me/notifications/badge", views.my_notifications_badge_view),
    path(
        "orgs/<uuid:org_id>/me/notifications/<uuid:notification_id>",
        views.my_notification_detail_view,
    ),
    path(
        "orgs/<uuid:org_id>/projects/<uuid:project_id>/notification-preferences",
        views.notification_preferences_view,
    ),
    path(
        "orgs/<uuid:org_id>/projects/<uuid:project_id>/notification-settings",
        views.notification_project_settings_view,
    ),
    path(
        "orgs/<uuid:org_id>/projects/<uuid:project_id>/notification-delivery-logs",
        views.notification_delivery_logs_view,
    ),
    path(
        "orgs/<uuid:org_id>/projects/<uuid:project_id>/notification-events",
        views.project_notification_events_view,
    ),
]
