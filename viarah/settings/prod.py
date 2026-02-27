import os

from .base import *  # noqa: F403

DEBUG = False  # noqa: F405

# Production security defaults (reverse-proxy friendly).
#
# Note: When `SESSION_COOKIE_SECURE` is enabled, operators must serve the app over HTTPS.
# For local verification without TLS, set `DJANGO_SECURE_COOKIES=0`.
_secure_cookies = os.environ.get("DJANGO_SECURE_COOKIES", "1").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

SESSION_COOKIE_SECURE = _secure_cookies  # noqa: F405
CSRF_COOKIE_SECURE = _secure_cookies  # noqa: F405

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # noqa: F405
USE_X_FORWARDED_HOST = True  # noqa: F405

SECURE_CONTENT_TYPE_NOSNIFF = True  # noqa: F405
SECURE_REFERRER_POLICY = "same-origin"  # noqa: F405
X_FRAME_OPTIONS = "DENY"  # noqa: F405
