from django.urls import path

from . import views

urlpatterns = [
    path("orgs/<uuid:org_id>/templates", views.templates_collection_view),
    path("orgs/<uuid:org_id>/templates/<uuid:template_id>", views.template_detail_view),
    path(
        "orgs/<uuid:org_id>/templates/<uuid:template_id>/versions",
        views.template_versions_collection_view,
    ),
    path(
        "orgs/<uuid:org_id>/templates/<uuid:template_id>/versions/<uuid:version_id>",
        views.template_version_detail_view,
    ),
]
