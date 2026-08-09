"""
CyberCraft — base settings.

Shared by every environment. This module imports nothing from its
siblings, which is what keeps the package acyclic: dev.py and prod.py
both do `from .base import *`, and base.py never reaches back.

Do not put environment-specific values here. Anything that differs
between development and production belongs in dev.py or prod.py.
"""

import os
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    SECRET_KEY=(str, ""),
    SERVERS_ROOT=(str, str(BASE_DIR / "servers")),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ORIGINS=(str, "http://localhost:3000,http://127.0.0.1:3000"),
    CSRF_TRUSTED_ORIGINS=(list, []),
    BACKEND_URL=(str, "http://127.0.0.1:8000"),
    EMAIL_BACKEND=(str, "django.core.mail.backends.console.EmailBackend"),
    EMAIL_HOST=(str, "smtp.gmail.com"),
    EMAIL_PORT=(int, 587),
    EMAIL_HOST_USER=(str, ""),
    EMAIL_HOST_PASSWORD=(str, ""),
    EMAIL_USE_TLS=(bool, True),
    DEFAULT_FROM_EMAIL=(str, "noreply@cybercraft.uz"),
    SITE_URL=(str, "http://localhost:3000"),
    GOOGLE_CLIENT_ID=(str, ""),
    TELEGRAM_BOT_TOKEN=(str, ""),
    REDIS_URL=(str, ""),
    DB_NAME=(str, ""),
    DB_USER=(str, ""),
    DB_PASSWORD=(str, ""),
    DB_HOST=(str, "localhost"),
    DB_PORT=(str, "5432"),
    THROTTLE_RATE_ANON=(str, "150/minute"),
    THROTTLE_RATE_USER=(str, "500/minute"),
    THROTTLE_RATE_SENSITIVE=(str, "5/minute"),
    SERVER_ZIP_MAX_UPLOAD_BYTES=(int, 2 * 1024 * 1024 * 1024),
)

env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env("SECRET_KEY")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# Absolute base URL of this backend, as reachable by Minecraft servers and
# the launcher. Injected into every managed server's authlib-injector
# javaagent argument by apps/servers/server_manager.py.
BACKEND_URL = env("BACKEND_URL").rstrip("/")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
    "apps.accounts.apps.AccountsConfig",
    "apps.launcher.apps.LauncherConfig",
    "apps.servers.apps.ServersConfig",
    "apps.news.apps.NewsConfig",
    "apps.voting.apps.VotingConfig",
    "apps.rewards.apps.RewardsConfig",
    "apps.auditlog.apps.AuditlogConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.yggdrasil_auth.apps.YggdrasilAuthConfig",
]

MIDDLEWARE = [
    "config.middleware.ShutdownMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "config.middleware.BanCheckMiddleware",
    "config.middleware.RequestLoggingMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Django 5.1 removed STATICFILES_STORAGE in favour of STORAGES.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

SERVERS_ROOT = Path(env("SERVERS_ROOT")).resolve()

SERVER_ZIP_MAX_UPLOAD_BYTES = env("SERVER_ZIP_MAX_UPLOAD_BYTES")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.AdminTokenAuthentication",
        "apps.launcher.authentication.LauncherTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_RATE_ANON"),
        "user": env("THROTTLE_RATE_USER"),
        "sensitive": env("THROTTLE_RATE_SENSITIVE"),
    },
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "config.exception_handler.custom_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "CyberCraft API",
    "DESCRIPTION": "CyberCraft Minecraft server management API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

CORS_ALLOWED_ORIGINS = [o for o in env("CORS_ORIGINS").split(",") if o]
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

EMAIL_BACKEND = env("EMAIL_BACKEND")
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env("EMAIL_PORT")
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env("EMAIL_USE_TLS")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")

SITE_URL = env("SITE_URL")
GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID") or None
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN") or None

LOG_DIR = BASE_DIR / "logs"

LOG_FORMATTERS = {
    "verbose": {
        "format": "[{asctime}] {levelname} {name}: {message}",
        "style": "{",
    },
}


def redis_backed(redis_url):
    """Cache and channel layer configuration for a given Redis URL.

    Returned as a pair so dev.py and prod.py can apply both without
    repeating the structure.
    """
    caches = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": redis_url,
        }
    }
    channel_layers = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [redis_url]},
        },
    }
    return caches, channel_layers


def locmem_backed():
    """In-process cache and channel layer, for single-process development."""
    caches = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "cybercraft-cache",
            "TIMEOUT": 300,
        }
    }
    channel_layers = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
    }
    return caches, channel_layers


def sqlite_database():
    return {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


def postgres_database():
    return {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME"),
            "USER": env("DB_USER"),
            "PASSWORD": env("DB_PASSWORD"),
            "HOST": env("DB_HOST"),
            "PORT": env("DB_PORT"),
            "CONN_MAX_AGE": 600,
            "OPTIONS": {"connect_timeout": 10},
        }
    }


# DATABASE_URL wins over the discrete DB_* variables when present. CI sets
# it, and it is the more portable form.
DATABASE_URL = os.environ.get("DATABASE_URL", "")
