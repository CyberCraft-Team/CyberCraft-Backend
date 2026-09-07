"""
CyberCraft — production settings.

Active when PRODUCTION is set in the environment.

Every value here is final: nothing runs after this module, so unlike the
previous settings.py / settings_prod.py arrangement, these are not
silently overwritten.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401, F403
from .base import (  # explicit, so linters see them
    BASE_DIR,
    DATABASE_URL,
    LOG_DIR,
    LOG_FORMATTERS,
    env,
    postgres_database,
    redis_backed,
    sqlite_database,
)

DEBUG = False

if not SECRET_KEY:  # noqa: F405
    raise ImproperlyConfigured("SECRET_KEY must be set when PRODUCTION is enabled.")

if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set when PRODUCTION is enabled.")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

if env.bool("USE_SQLITE", False):
    DATABASES = sqlite_database()
elif DATABASE_URL:
    DATABASES = {"default": env.db_url_config(DATABASE_URL)}
    DATABASES["default"].setdefault("CONN_MAX_AGE", 600)
else:
    DATABASES = postgres_database()
    if not DATABASES["default"]["NAME"]:
        raise ImproperlyConfigured(
            "Set DATABASE_URL, or DB_NAME/DB_USER/DB_PASSWORD, or USE_SQLITE=1."
        )

# ---------------------------------------------------------------------------
# Cache and channel layer
#
# Redis is required. The channel layer carries live server console output
# between the web process and the supervisor, and an in-memory layer cannot
# cross process boundaries -- that silently broke under the old settings.
# ---------------------------------------------------------------------------

_redis_url = env("REDIS_URL")
if not _redis_url:
    raise ImproperlyConfigured(
        "REDIS_URL is required in production: the channel layer must be shared "
        "across processes."
    )

CACHES, CHANNEL_LAYERS = redis_backed(_redis_url)

if not MOD_API_KEY:  # noqa: F405
    raise ImproperlyConfigured(
        "MOD_API_KEY is required in production: /minecraft/verify/ decides who "
        "may join a game server, and it would otherwise accept any caller."
    )

# ---------------------------------------------------------------------------
# Security
#
# USE_SSL stays configurable because the first deployment may run on a bare
# LAN address before a certificate exists.
# ---------------------------------------------------------------------------

_USE_SSL = env.bool("USE_SSL", False)

SECURE_SSL_REDIRECT = _USE_SSL
SESSION_COOKIE_SECURE = _USE_SSL
CSRF_COOKIE_SECURE = _USE_SSL

if _USE_SSL:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # the SPA reads this token

# ---------------------------------------------------------------------------
# Throttling — tighter than development
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_RATE_ANON", default="30/minute"),
        "user": env("THROTTLE_RATE_USER", default="120/minute"),
        "sensitive": env("THROTTLE_RATE_SENSITIVE", default="5/minute"),
    },
}

# ---------------------------------------------------------------------------
# Logging — rotating files alongside the console
# ---------------------------------------------------------------------------

LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": LOG_FORMATTERS,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "api_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "api.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "error.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
            "level": "ERROR",
        },
        "security_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "security.log"),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 3,
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "error_file"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.server": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console", "security_file"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console", "api_file", "error_file"],
            "level": "INFO",
            "propagate": False,
        },
        "api.requests": {
            "handlers": ["console", "api_file"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {"handlers": ["console", "error_file"], "level": "WARNING"},
}

# ---------------------------------------------------------------------------
# Email — switch to SMTP when a host is configured
# ---------------------------------------------------------------------------

if env("EMAIL_HOST") and env("EMAIL_HOST_USER"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# ---------------------------------------------------------------------------
# Media
#
# nginx serves /media/ and /static/ directly; see deploy/nginx.conf. Django
# never sees those requests in production.
# ---------------------------------------------------------------------------

_ = BASE_DIR  # referenced by deploy docs; keeps the import meaningful
