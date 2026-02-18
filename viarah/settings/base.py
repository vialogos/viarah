import os
from pathlib import Path

import dj_database_url


def _require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"{name} environment variable is required")
    return value


BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = _require_env("DJANGO_SECRET_KEY")

DEBUG = os.environ.get("DJANGO_DEBUG", "0").lower() in {"1", "true", "yes", "on"}

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]
if not ALLOWED_HOSTS:
    # Safe defaults for local dev + Django's test client (`testserver`).
    ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "identity.apps.IdentityConfig",
    "audit.apps.AuditConfig",
    "api_keys.apps.ApiKeysConfig",
    "workflows.apps.WorkflowsConfig",
    "work_items.apps.WorkItemsConfig",
    "notifications.apps.NotificationsConfig",
    "templates.apps.TemplatesConfig",
    "reports.apps.ReportsConfig",
    "sows.apps.SowsConfig",
    "share_links.apps.ShareLinksConfig",
    "collaboration.apps.CollaborationConfig",
    "outbound_comms.apps.OutboundCommsConfig",
    "customization.apps.CustomizationConfig",
    "realtime.apps.RealtimeConfig",
    "core.apps.CoreConfig",
    "push.apps.PushConfig",
    "integrations.apps.IntegrationsConfig",
]

AUTH_USER_MODEL = "identity.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "api_keys.middleware.ApiKeyCsrfBypassMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "api_keys.middleware.ApiKeyAuthMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "viarah.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

ASGI_APPLICATION = "viarah.asgi.application"
WSGI_APPLICATION = "viarah.wsgi.application"

DATABASES = {"default": dj_database_url.parse(_require_env("DATABASE_URL"), conn_max_age=60)}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", str(BASE_DIR / "uploads"))

EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "25") or "25")
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "0").lower() in {"1", "true", "yes", "on"}
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "no-reply@viarah.local")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CELERY_BROKER_URL = _require_env("CELERY_BROKER_URL")
CELERY_TASK_IGNORE_RESULT = True
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_TASK_ALWAYS_EAGER = os.environ.get("CELERY_TASK_ALWAYS_EAGER", "0").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
CELERY_TASK_EAGER_PROPAGATES = True

WEBPUSH_VAPID_PUBLIC_KEY = os.environ.get("WEBPUSH_VAPID_PUBLIC_KEY", "").strip()
WEBPUSH_VAPID_PRIVATE_KEY = os.environ.get("WEBPUSH_VAPID_PRIVATE_KEY", "").strip()
WEBPUSH_VAPID_SUBJECT = os.environ.get("WEBPUSH_VAPID_SUBJECT", "").strip()

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [CELERY_BROKER_URL]},
    }
}
