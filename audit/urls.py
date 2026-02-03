from django.urls import path

from . import views

urlpatterns = [
    path("orgs/<uuid:org_id>/audit-events", views.list_audit_events_view),
]
