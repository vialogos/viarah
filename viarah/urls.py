from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("identity.urls")),
    path("api/", include("audit.urls")),
    path("", include("core.urls")),
]
