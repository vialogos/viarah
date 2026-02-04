from django.urls import path

from . import public_views

urlpatterns = [
    path("r/<str:token>", public_views.public_share_link_view),
]

