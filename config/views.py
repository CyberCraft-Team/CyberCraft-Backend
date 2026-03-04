"""Health check and utility views."""

import time
from django.db import connection
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny


class HealthCheckView(APIView):
    """System health check — DB, disk, uptime."""

    permission_classes = [AllowAny]
    authentication_classes = []

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
        except Exception as e:
            health["status"] = "error"
            health["checks"]["database"] = {
                "status": "error",
                "error": str(e),
            }

        media_root = settings.MEDIA_ROOT
        health["checks"]["media_storage"] = {
            "status": "ok" if media_root.exists() else "error",
            "path": str(media_root),
        }

        status_code = 200 if health["status"] == "ok" else 503
        return Response(health, status=status_code)
