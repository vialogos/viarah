from django.urls import path

from . import views

urlpatterns = [
    path("settings/integrations/gitlab", views.settings_gitlab_integration_view),
    path("orgs/<uuid:org_id>/integrations/gitlab", views.org_gitlab_integration_view),
    path(
        "orgs/<uuid:org_id>/integrations/gitlab/validate",
        views.gitlab_integration_validate_view,
    ),
    path(
        "orgs/<uuid:org_id>/tasks/<uuid:task_id>/gitlab-links",
        views.task_gitlab_links_collection_view,
    ),
    path(
        "orgs/<uuid:org_id>/tasks/<uuid:task_id>/gitlab-links/<uuid:link_id>",
        views.task_gitlab_link_delete_view,
    ),
    path(
        "orgs/<uuid:org_id>/integrations/gitlab/webhook",
        views.gitlab_webhook_view,
    ),
]
