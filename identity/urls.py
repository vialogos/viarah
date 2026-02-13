from django.urls import path

from . import views

urlpatterns = [
    path("auth/login", views.login_view),
    path("auth/logout", views.logout_view),
    path("me", views.me_view),
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
    path("orgs/<uuid:org_id>/people/<uuid:person_id>", views.person_detail_view),
    path(
        "orgs/<uuid:org_id>/people/<uuid:person_id>/invite",
        views.person_invite_view,
    ),
    path("orgs/<uuid:org_id>/memberships", views.org_memberships_collection_view),
    path(
        "orgs/<uuid:org_id>/memberships/<uuid:membership_id>",
        views.update_membership_view,
    ),
]
