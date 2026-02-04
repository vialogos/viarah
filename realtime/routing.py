from django.urls import path

from .consumers import OrgEventsConsumer

websocket_urlpatterns = [
    path("ws/orgs/<uuid:org_id>/events", OrgEventsConsumer.as_asgi()),
]
