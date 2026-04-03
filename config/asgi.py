import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from urllib.parse import parse_qs

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_app = get_asgi_application()

from apps.servers.routing import websocket_urlpatterns


class TokenAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        from django.contrib.auth.models import AnonymousUser

        query_string = scope.get("query_string", b"").decode()
        query_params = parse_qs(query_string)
        token_key = query_params.get("token", [None])[0]

        if token_key:
            scope["user"] = await self.get_user_from_token(token_key)
        else:
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)

    @database_sync_to_async
    def get_user_from_token(self, token_key):
        from django.contrib.auth.models import AnonymousUser
        from apps.launcher.models import LauncherToken
        from apps.accounts.models import AdminToken

        # 1. Launcher tokenni tekshiramiz
        try:
            token = LauncherToken.objects.select_related("user").get(key=token_key)
            if not token.is_expired():
                return token.user
        except LauncherToken.DoesNotExist:
            pass

        # 2. Admin tokenni tekshiramiz (web dashboard uchun)
        try:
            token = AdminToken.objects.select_related("user").get(key=token_key)
            if not token.is_expired():
                return token.user
        except AdminToken.DoesNotExist:
            pass

        return AnonymousUser()


class ASGIShutdownMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        from apps.servers.server_manager import MinecraftServerManager

        if MinecraftServerManager._is_shutting_down:
            if scope["type"] == "http":
                await send(
                    {
                        "type": "http.response.start",
                        "status": 503,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                import json

                await send(
                    {
                        "type": "http.response.body",
                        "body": json.dumps(
                            {"error": "Server o'chirilmoqda", "code": "shutting_down"}
                        ).encode(),
                    }
                )
                return
            elif scope["type"] == "websocket":
                # WebSocket ulanishini rad etamiz
                await send({"type": "websocket.close", "code": 1001})
                return

        return await self.app(scope, receive, send)


application = ASGIShutdownMiddleware(
    ProtocolTypeRouter(
        {
            "http": django_asgi_app,
            "websocket": TokenAuthMiddleware(URLRouter(websocket_urlpatterns)),
        }
    )
)
