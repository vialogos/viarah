from django.urls import path

from . import views

urlpatterns = [
    path("push/vapid_public_key", views.vapid_public_key_view),
    path("push/vapid_config", views.vapid_config_view),
    path("push/vapid_config/generate", views.vapid_config_generate_view),
    path("push/subscriptions", views.subscriptions_collection_view),
    path("push/subscriptions/<uuid:subscription_id>", views.subscription_detail_view),
]
