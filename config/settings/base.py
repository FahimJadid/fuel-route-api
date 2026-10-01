from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env()

SECRET_KEY = env("SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "rest_framework",
    "drf_spectacular",
    "core",
    "geo",
    "stations",
    "routing",
]

MIDDLEWARE = [
    "core.middleware.RequestLoggingMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    },
]

DATABASES = {
    "default": env.db("DATABASE_URL") | {"CONN_MAX_AGE": 60, "CONN_HEALTH_CHECKS": True},
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL"),
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "core.exceptions.exception_handler",
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.server": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "httpx": {"level": "WARNING"},
    },
}

ROUTING = {
    "OSRM_BASE_URL": env("OSRM_BASE_URL", default="https://router.project-osrm.org"),
    "TIMEOUT_SECONDS": env.float("ROUTING_TIMEOUT_SECONDS", default=10.0),
    "USER_AGENT": "fuel-route-api/0.1",
    "SIMPLIFY_TOLERANCE_DEGREES": 0.001,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Fuel Route API",
    "DESCRIPTION": "Plans cost-optimal fuel stops along a driving route within the USA.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}
