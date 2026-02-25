from django.urls import path

from . import views

urlpatterns = [
    path("", views.index),
    path("manifest.webmanifest", views.manifest_webmanifest),
    path("service-worker.js", views.service_worker_js),
    path("healthz", views.healthz),
]
