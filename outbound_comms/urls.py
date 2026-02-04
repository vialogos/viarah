from django.urls import path

from . import views

urlpatterns = [
    path(
        "orgs/<uuid:org_id>/projects/<uuid:project_id>/outbound-drafts",
        views.outbound_drafts_collection_view,
    ),
    path("orgs/<uuid:org_id>/outbound-drafts/<uuid:draft_id>", views.outbound_draft_detail_view),
    path(
        "orgs/<uuid:org_id>/outbound-drafts/<uuid:draft_id>/send",
        views.outbound_draft_send_view,
    ),
]
