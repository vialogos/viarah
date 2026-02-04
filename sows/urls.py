from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("orgs/<uuid:org_id>/sows", views.sows_collection_view),
    path("orgs/<uuid:org_id>/sows/<uuid:sow_id>", views.sow_detail_view),
    path("orgs/<uuid:org_id>/sows/<uuid:sow_id>/send", views.sow_send_view),
    path("orgs/<uuid:org_id>/sows/<uuid:sow_id>/respond", views.sow_respond_view),
    path("orgs/<uuid:org_id>/sows/<uuid:sow_id>/versions", views.sow_versions_collection_view),
    path("orgs/<uuid:org_id>/sows/<uuid:sow_id>/pdf", views.sow_pdf_view),
]
