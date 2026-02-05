from django.urls import path

from . import views

urlpatterns = [
    path("auth/login", views.login_view),
    path("auth/logout", views.logout_view),
    path("me", views.me_view),
    path("invites/accept", views.accept_invite_view),
    path("orgs/<uuid:org_id>/invites", views.create_org_invite_view),
    path("orgs/<uuid:org_id>/memberships", views.org_memberships_collection_view),
    path("orgs/<uuid:org_id>/memberships/<uuid:membership_id>", views.update_membership_view),
]
