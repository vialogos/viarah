from django.urls import path

from . import views

urlpatterns = [
    path("api-keys", views.api_keys_collection_view),
    path("api-keys/<uuid:api_key_id>/revoke", views.revoke_api_key_view),
    path("api-keys/<uuid:api_key_id>/rotate", views.rotate_api_key_view),
]

