from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("identity.urls")),
    path("api/", include("audit.urls")),
    path("api/", include("api_keys.urls")),
    path("api/", include("workflows.urls")),
    path("api/", include("work_items.urls")),
    path("api/", include("templates.urls")),
    path("api/", include("reports.urls")),
    path("api/", include("collaboration.urls")),
    path("api/", include("customization.urls")),
    path("api/", include("integrations.urls")),
    path("", include("core.urls")),
]
