from django.urls import path

from . import views

urlpatterns = [
    path("orgs/<uuid:org_id>/projects", views.projects_collection_view),
    path("orgs/<uuid:org_id>/projects/<uuid:project_id>", views.project_detail_view),
    path(
        "orgs/<uuid:org_id>/projects/<uuid:project_id>/memberships",
        views.project_memberships_collection_view,
    ),
    path(
        "orgs/<uuid:org_id>/projects/<uuid:project_id>/memberships/<uuid:membership_id>",
        views.project_membership_detail_view,
    ),
    path(
        "orgs/<uuid:org_id>/projects/<uuid:project_id>/epics",
        views.project_epics_collection_view,
    ),
    path("orgs/<uuid:org_id>/epics/<uuid:epic_id>", views.epic_detail_view),
    path("orgs/<uuid:org_id>/epics/<uuid:epic_id>/tasks", views.epic_tasks_collection_view),
    path(
        "orgs/<uuid:org_id>/projects/<uuid:project_id>/tasks",
        views.project_tasks_list_view,
    ),
    path("orgs/<uuid:org_id>/tasks/<uuid:task_id>", views.task_detail_view),
    path(
        "orgs/<uuid:org_id>/tasks/<uuid:task_id>/subtasks",
        views.task_subtasks_collection_view,
    ),
    path("orgs/<uuid:org_id>/subtasks/<uuid:subtask_id>", views.subtask_detail_view),
]
