from django.urls import path

from . import views

urlpatterns = [
    path("auth/login", views.login_view),
    path("auth/logout", views.logout_view),
    path("me", views.me_view),
    path("settings/defaults", views.settings_defaults_view),
    path("orgs", views.orgs_collection_view),
    path("orgs/<uuid:org_id>", views.org_detail_view),
    path("orgs/<uuid:org_id>/logo", views.org_logo_view),
    path("orgs/<uuid:org_id>/defaults", views.org_defaults_view),
    path("invites/accept", views.accept_invite_view_v2),
    path("orgs/<uuid:org_id>/invites", views.org_invites_collection_view),
    path(
        "orgs/<uuid:org_id>/invites/<uuid:invite_id>/revoke",
        views.org_invite_revoke_view,
    ),
    path(
        "orgs/<uuid:org_id>/invites/<uuid:invite_id>/resend",
        views.org_invite_resend_view,
    ),
    path("orgs/<uuid:org_id>/people", views.org_people_collection_view),
    path("orgs/<uuid:org_id>/people/me", views.my_person_view),
    path("orgs/<uuid:org_id>/people/<uuid:person_id>", views.person_detail_view),
    path(
        "orgs/<uuid:org_id>/people/<uuid:person_id>/avatar",
        views.person_avatar_view,
    ),
    path(
        "orgs/<uuid:org_id>/people/<uuid:person_id>/project-memberships",
        views.person_project_memberships_view,
    ),
    path(
        "orgs/<uuid:org_id>/people/<uuid:person_id>/invite",
        views.person_invite_view,
    ),
    path(
        "orgs/<uuid:org_id>/people/<uuid:person_id>/contact-entries",
        views.person_contact_entries_collection_view,
    ),
    path(
        "orgs/<uuid:org_id>/people/<uuid:person_id>/contact-entries/<uuid:entry_id>",
        views.person_contact_entry_detail_view,
    ),
    path(
        "orgs/<uuid:org_id>/people/<uuid:person_id>/message-threads",
        views.person_message_threads_collection_view,
    ),
    path(
        "orgs/<uuid:org_id>/people/<uuid:person_id>/message-threads/<uuid:thread_id>",
        views.person_message_thread_detail_view,
    ),
    path(
        "orgs/<uuid:org_id>/people/<uuid:person_id>/message-threads/<uuid:thread_id>/messages",
        views.person_messages_collection_view,
    ),
    path("orgs/<uuid:org_id>/people/<uuid:person_id>/rates", views.person_rates_collection_view),
    path(
        "orgs/<uuid:org_id>/people/<uuid:person_id>/rates/<uuid:rate_id>",
        views.person_rate_detail_view,
    ),
    path(
        "orgs/<uuid:org_id>/people/<uuid:person_id>/payments",
        views.person_payments_collection_view,
    ),
    path(
        "orgs/<uuid:org_id>/people/<uuid:person_id>/payments/<uuid:payment_id>",
        views.person_payment_detail_view,
    ),
    path(
        "orgs/<uuid:org_id>/people/availability-search", views.org_people_availability_search_view
    ),
    path("orgs/<uuid:org_id>/people/<uuid:person_id>/availability", views.person_availability_view),
    path(
        "orgs/<uuid:org_id>/people/<uuid:person_id>/availability/weekly-windows",
        views.person_weekly_windows_create_view,
    ),
    path(
        "orgs/<uuid:org_id>/people/<uuid:person_id>/availability/weekly-windows/<uuid:weekly_window_id>",
        views.person_weekly_window_detail_view,
    ),
    path(
        "orgs/<uuid:org_id>/people/<uuid:person_id>/availability/exceptions",
        views.person_availability_exceptions_create_view,
    ),
    path(
        "orgs/<uuid:org_id>/people/<uuid:person_id>/availability/exceptions/<uuid:exception_id>",
        views.person_availability_exception_detail_view,
    ),
    path("orgs/<uuid:org_id>/clients", views.org_clients_collection_view),
    path("orgs/<uuid:org_id>/clients/<uuid:client_id>", views.client_detail_view),
    path("orgs/<uuid:org_id>/memberships", views.org_memberships_collection_view),
    path(
        "orgs/<uuid:org_id>/memberships/<uuid:membership_id>",
        views.update_membership_view,
    ),
]
