import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

logger = logging.getLogger(__name__)


class WSTokenAuthMixin:
    """WS Token autentifikatsiyasi uchun mixin"""

    @database_sync_to_async
    def get_user_from_ws_token(self, token_key):
        from apps.launcher.models import WSToken
        from django.contrib.auth.models import AnonymousUser

        try:
            token = WSToken.objects.select_related("user").get(key=token_key)
            if not token.is_expired():
                return token.user
        except WSToken.DoesNotExist:
            pass
        return AnonymousUser()


class LauncherStatusConsumer(WSTokenAuthMixin, AsyncWebsocketConsumer):
    """Real-time server status yangilanishlari"""

    async def connect(self):
        query_string = self.scope.get("query_string", b"").decode()
        from urllib.parse import parse_qs
        query_params = parse_qs(query_string)
        token_key = query_params.get("token", [None])[0]

        if not token_key:
            await self.close(code=4001)
            return

        self.user = await self.get_user_from_ws_token(token_key)
        if self.user.is_anonymous:
            await self.close(code=4001)
            return

        self.group_name = "launcher_status"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        await self.send_initial_status()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def send_initial_status(self):
        from apps.servers.models import MinecraftServer, Server
        from django.db.models import Count

        managed_servers = await database_sync_to_async(list)(
            MinecraftServer.objects.select_related("server_type").all()
        )
        external_servers = await database_sync_to_async(list)(
            Server.objects.filter(is_active=True).all()
        )

        servers_data = []
        for server in managed_servers:
            servers_data.append({
                "id": str(server.id),
                "name": server.name,
                "status": server.status,
                "current_players": server.current_players,
                "max_players": server.max_players,
                "is_managed": True,
            })

        for server in external_servers:
            servers_data.append({
                "id": str(server.id),
                "name": server.name,
                "status": server.status,
                "current_players": server.current_players,
                "max_players": server.max_players,
                "is_managed": False,
            })

        await self.send(text_data=json.dumps({
            "type": "status_update",
            "servers": servers_data,
            "timestamp": timezone.now().isoformat(),
        }))

    async def status_update(self, event):
        await self.send(text_data=json.dumps(event["data"]))


class LauncherConsoleConsumer(WSTokenAuthMixin, AsyncWebsocketConsumer):
    """Minecraft server console log stream"""

    async def connect(self):
        query_string = self.scope.get("query_string", b"").decode()
        from urllib.parse import parse_qs
        query_params = parse_qs(query_string)
        token_key = query_params.get("token", [None])[0]

        if not token_key:
            await self.close(code=4001)
            return

        self.user = await self.get_user_from_ws_token(token_key)
        if self.user.is_anonymous:
            await self.close(code=4001)
            return

        self.server_id = self.scope["url_route"]["kwargs"]["server_id"]
        self.group_name = f"server_{self.server_id}"

        from apps.servers.models import MinecraftServer
        try:
            server = await database_sync_to_async(MinecraftServer.objects.get)(id=self.server_id)
            self.server = server
        except MinecraftServer.DoesNotExist:
            await self.close(code=4004)
            return
        if server.owner_id != self.user.id and not self.user.is_staff:
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def console_log(self, event):
        await self.send(text_data=json.dumps({
            "type": "console_log",
            "line": event["line"],
            "timestamp": event.get("timestamp", timezone.now().isoformat()),
        }))

    async def server_log(self, event):
        log = event.get("log", {})
        await self.send(text_data=json.dumps({
            "type": "console_log",
            "line": log.get("message", ""),
            "level": log.get("level", "info"),
            "timestamp": log.get("timestamp", timezone.now().isoformat()),
        }))

    async def server_status(self, event):
        await self.send(text_data=json.dumps({
            "type": "server_status",
            "status": event.get("status"),
            "timestamp": timezone.now().isoformat(),
        }))


class LauncherEventsConsumer(WSTokenAuthMixin, AsyncWebsocketConsumer):
    """Launch progress, update notifications"""

    async def connect(self):
        query_string = self.scope.get("query_string", b"").decode()
        from urllib.parse import parse_qs
        query_params = parse_qs(query_string)
        token_key = query_params.get("token", [None])[0]

        if not token_key:
            await self.close(code=4001)
            return

        self.user = await self.get_user_from_ws_token(token_key)
        if self.user.is_anonymous:
            await self.close(code=4001)
            return

        self.group_name = f"launcher_events_{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def launch_progress(self, event):
        await self.send(text_data=json.dumps({
            "type": "launch_progress",
            "state": event["state"],
            "progress": event["progress"],
            "message": event["message"],
        }))

    async def update_notification(self, event):
        await self.send(text_data=json.dumps({
            "type": "update_notification",
            "version": event["version"],
            "download_url": event["download_url"],
            "force": event.get("force", False),
            "release_notes": event.get("release_notes", ""),
        }))
