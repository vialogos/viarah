from django.urls import path

from . import views

urlpatterns = [
    path("orgs/<uuid:org_id>/report-runs", views.report_runs_collection_view),
    path("orgs/<uuid:org_id>/report-runs/<uuid:report_run_id>", views.report_run_detail_view),
    path(
        "orgs/<uuid:org_id>/report-runs/<uuid:report_run_id>/regenerate",
        views.report_run_regenerate_view,
    ),
    path(
        "orgs/<uuid:org_id>/report-runs/<uuid:report_run_id>/web-view",
        views.report_run_web_view,
    ),
]
