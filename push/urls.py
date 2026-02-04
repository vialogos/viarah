from django.urls import path

from . import views

urlpatterns = [
    path("push/vapid_public_key", views.vapid_public_key_view),
    path("push/subscriptions", views.subscriptions_collection_view),
    path("push/subscriptions/<uuid:subscription_id>", views.subscription_detail_view),
]
