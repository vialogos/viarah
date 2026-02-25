from django.urls import path

from . import views

urlpatterns = [
    path("orgs/<uuid:org_id>/workflows", views.workflows_collection_view),
    path("orgs/<uuid:org_id>/workflows/<uuid:workflow_id>", views.workflow_detail_view),
    path(
        "orgs/<uuid:org_id>/workflows/<uuid:workflow_id>/stages",
        views.workflow_stages_collection_view,
    ),
    path(
        "orgs/<uuid:org_id>/workflows/<uuid:workflow_id>/stages/<uuid:stage_id>",
        views.workflow_stage_detail_view,
    ),
]
