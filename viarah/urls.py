from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("identity.urls")),
    path("api/", include("audit.urls")),
    path("api/", include("api_keys.urls")),
    path("api/", include("workflows.urls")),
    path("api/", include("work_items.urls")),
    path("api/", include("customization.urls")),
    path("", include("core.urls")),
]
