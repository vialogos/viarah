from django.urls import path

from . import views

urlpatterns = [
    path(
        "orgs/<uuid:org_id>/projects/<uuid:project_id>/saved-views",
        views.saved_views_collection_view,
    ),
    path("orgs/<uuid:org_id>/saved-views/<uuid:saved_view_id>", views.saved_view_detail_view),
    path(
        "orgs/<uuid:org_id>/projects/<uuid:project_id>/custom-fields",
        views.custom_fields_collection_view,
    ),
    path("orgs/<uuid:org_id>/custom-fields/<uuid:field_id>", views.custom_field_detail_view),
    path(
        "orgs/<uuid:org_id>/tasks/<uuid:task_id>/custom-field-values",
        views.task_custom_field_values_view,
    ),
    path(
        "orgs/<uuid:org_id>/subtasks/<uuid:subtask_id>/custom-field-values",
        views.subtask_custom_field_values_view,
    ),
]
