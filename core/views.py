from django.db import connections
from django.http import HttpResponse


def index(_request):
    return HttpResponse("viarah", content_type="text/plain")


def healthz(_request):
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
    except Exception:
        return HttpResponse("unhealthy", status=503, content_type="text/plain")

    return HttpResponse("ok", content_type="text/plain")
