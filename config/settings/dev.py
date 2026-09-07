"""
CyberCraft — development settings.

Active unless PRODUCTION is set in the environment.
"""

from .base import *  # noqa: F401, F403
from .base import (  # explicit, so linters see them
    LOG_FORMATTERS,
    env,
    locmem_backed,
    redis_backed,
    sqlite_database,
)

DEBUG = env.bool("DEBUG", True)

if not SECRET_KEY:  # noqa: F405
    # Development convenience only. prod.py refuses to start without a real
    # key, so this can never leak into production.
    SECRET_KEY = "django-insecure-dev-only-key-do-not-use-in-production"  # noqa: F405

DATABASES = sqlite_database()

_redis_url = env("REDIS_URL")
if _redis_url:
    CACHES, CHANNEL_LAYERS = redis_backed(_redis_url)
else:
    CACHES, CHANNEL_LAYERS = locmem_backed()

# Minecraft MCEF and the file:// protocol both send opaque origins, and the
# Google OAuth popup relies on window.postMessage across origins, which
# Django's default same-origin COOP would block.
CORS_ALLOW_ALL_ORIGINS = True
SECURE_CROSS_ORIGIN_OPENER_POLICY = None

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": LOG_FORMATTERS,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.server": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "api.requests": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
