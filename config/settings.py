from pathlib import Path
import os
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, True),
    SECRET_KEY=(str,),
    SERVERS_ROOT=(str, str(BASE_DIR / "servers")),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ORIGINS=(str, "http://localhost:3000,http://127.0.0.1:3000"),
    EMAIL_BACKEND=(str, "django.core.mail.backends.console.EmailBackend"),
    EMAIL_HOST=(str, "smtp.gmail.com"),
    EMAIL_PORT=(int, 587),
    EMAIL_HOST_USER=(str, ""),
    EMAIL_HOST_PASSWORD=(str, ""),
    EMAIL_USE_TLS=(bool, True),
    DEFAULT_FROM_EMAIL=(str, "noreply@cybercraft.uz"),
    SITE_URL=(str, "http://localhost:3000"),
    GOOGLE_CLIENT_ID=(str, None),
    TELEGRAM_BOT_TOKEN=(str, None),
)

env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

if os.environ.get("PRODUCTION"):
    from .settings_prod import *
else:
    SECRET_KEY = env("SECRET_KEY")
    DEBUG = env("DEBUG")

ALLOWED_HOSTS = env("ALLOWED_HOSTS")


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
    "rest_framework.authtoken",
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

CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "cybercraft-cache",
        "TIMEOUT": 300,
    }
}


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


STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

SERVERS_ROOT = Path(env("SERVERS_ROOT")).resolve()

# ZIP orqali server yuklash (baytlarda, default 2 GB)
SERVER_ZIP_MAX_UPLOAD_BYTES = int(
    os.environ.get("SERVER_ZIP_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024))
)


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
        "anon": env("THROTTLE_RATE_ANON", default="150/minute"),
        "user": env("THROTTLE_RATE_USER", default="500/minute"),
        "sensitive": env("THROTTLE_RATE_SENSITIVE", default="5/minute"),
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

CORS_ALLOWED_ORIGINS = env("CORS_ORIGINS").split(",")
CORS_ALLOW_CREDENTIALS = True

# DEBUG rejimda barcha originlardan so'rovlarni qabul qilish
# (Minecraft MCEF va file:// protokoli uchun kerak)
if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
    # Google OAuth popup window.postMessage ishlatadi.
    # Django default COOP "same-origin" bu cross-origin xabarni bloklaydi.
    # Development da o'chirib qo'yamiz:
    SECURE_CROSS_ORIGIN_OPENER_POLICY = None

EMAIL_BACKEND = env("EMAIL_BACKEND")
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env("EMAIL_PORT")
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env("EMAIL_USE_TLS")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")
SITE_URL = env("SITE_URL")
GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID")
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.server": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "api.requests": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
