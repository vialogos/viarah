from django.urls import path

from . import views

urlpatterns = [
    path(
        "orgs/<uuid:org_id>/report-runs/<uuid:report_run_id>/publish",
        views.publish_share_link_view,
    ),
    path("orgs/<uuid:org_id>/share-links", views.share_links_collection_view),
    path(
        "orgs/<uuid:org_id>/share-links/<uuid:share_link_id>/revoke",
        views.revoke_share_link_view,
    ),
    path(
        "orgs/<uuid:org_id>/share-links/<uuid:share_link_id>/access-logs",
        views.share_link_access_logs_view,
    ),
]
