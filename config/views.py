"""Health check and utility views."""

import logging
import time
from django.db import connection
from django.core.cache import cache
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

logger = logging.getLogger(__name__)


class HealthCheckView(APIView):
    """System health check — DB, disk, uptime."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []  # Readiness must still report failures when Redis is down.

    def get(self, request):
        health = {
            "status": "ok",
            "checks": {},
        }

        try:
            start = time.monotonic()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            db_time = (time.monotonic() - start) * 1000
            health["checks"]["database"] = {
                "status": "ok",
                "response_time_ms": round(db_time, 2),
            }
        except Exception:
            logger.exception("Health check database probe failed")
            health["status"] = "error"
            health["checks"]["database"] = {
                "status": "error",
            }

        if "redis" in settings.CACHES["default"]["BACKEND"].lower():
            try:
                cache.get("cybercraft:readiness")
                health["checks"]["cache"] = {"status": "ok"}
            except Exception:
                logger.exception("Health check Redis probe failed")
                health["status"] = "error"
                health["checks"]["cache"] = {"status": "error"}

        media_root = settings.MEDIA_ROOT
        health["checks"]["media_storage"] = {
            "status": "ok" if media_root.exists() else "error",
        }

        if health["checks"]["media_storage"]["status"] != "ok":
            health["status"] = "error"

        status_code = 200 if health["status"] == "ok" else 503
        return Response(health, status=status_code)
