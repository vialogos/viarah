from django.urls import path

from . import views

urlpatterns = [
    path(
        "orgs/<uuid:org_id>/tasks/<uuid:task_id>/comments",
        views.task_comments_collection_view,
    ),
    path(
        "orgs/<uuid:org_id>/epics/<uuid:epic_id>/comments",
        views.epic_comments_collection_view,
    ),
    path(
        "orgs/<uuid:org_id>/tasks/<uuid:task_id>/attachments",
        views.task_attachments_collection_view,
    ),
    path(
        "orgs/<uuid:org_id>/epics/<uuid:epic_id>/attachments",
        views.epic_attachments_collection_view,
    ),
    path(
        "orgs/<uuid:org_id>/attachments/<uuid:attachment_id>/download",
        views.attachment_download_view,
    ),
]
