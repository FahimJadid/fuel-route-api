from .base import *  # noqa: F403

DEBUG = False

CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}
