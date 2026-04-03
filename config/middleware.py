"""
Custom middleware: Request Logging + Ban Check.
"""

import time
import logging
from django.http import JsonResponse
from django.utils import timezone

logger = logging.getLogger("api.requests")


class RequestLoggingMiddleware:
    """Barcha API so'rovlarni log qiladi: method, path, status, duration, user."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.monotonic()

        response = self.get_response(request)

        if request.path.startswith("/api/"):
            duration = (time.monotonic() - start_time) * 1000
            user = getattr(request, "user", None)
            username = user.username if user and user.is_authenticated else "anonymous"
            ip = self._get_client_ip(request)

            logger.info(
                "%s %s %s %dms [user=%s ip=%s]",
                request.method,
                request.path,
                response.status_code,
                duration,
                username,
                ip,
            )

        return response

    @staticmethod
    def _get_client_ip(request):
        x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded:
            return x_forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")


class BanCheckMiddleware:
    """Banned foydalanuvchilarni tekshiradi va API so'rovlarni bloklaydi."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/api/") and hasattr(request, "user"):
            user = request.user
            if user.is_authenticated:
                is_banned = getattr(user, "is_banned", False)
                banned_until = getattr(user, "banned_until", None)

                if banned_until and banned_until <= timezone.now():
                    user.is_banned = False
                    user.banned_until = None
                    user.ban_reason = ""
                    user.save(update_fields=["is_banned", "banned_until", "ban_reason"])
                elif is_banned:
                    reason = getattr(user, "ban_reason", "")
                    return JsonResponse(
                        {
                            "error": f"Sizning akkauntingiz bloklangan. Sabab: {reason}",
                            "code": "banned",
                            "banned_until": (
                                str(banned_until) if banned_until else "permanent"
                            ),
                        },
                        status=403,
                    )

        return self.get_response(request)


class ShutdownMiddleware:
    """Backend o'chirilayotganda yangi so'rovlarni 503 xatosi bilan qaytaradi."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from apps.servers.server_manager import MinecraftServerManager

        if MinecraftServerManager._is_shutting_down:
            return JsonResponse(
                {"error": "Server o'chirilmoqda", "code": "shutting_down"}, status=503
            )

        return self.get_response(request)
