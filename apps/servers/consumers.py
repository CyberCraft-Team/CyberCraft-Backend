import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


class ServerConsoleConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.server_id = self.scope["url_route"]["kwargs"]["server_id"]
        self.room_group_name = f"server_{self.server_id}"

        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close()
            return

        has_access = await self.check_server_access(user, self.server_id)
        if not has_access:
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        await self.accept()

        logs = await self.get_recent_logs(self.server_id)
        await self.send(json.dumps({"type": "initial_logs", "logs": logs}))

        status_info = await self.get_server_status(self.server_id)
        await self.send(
            json.dumps({"type": "server_status", "status": status_info["status"]})
        )

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get("type")

        if message_type == "command":
            command = data.get("command", "").strip()
            if command:
                user = self.scope.get("user")
                success = await self.send_server_command(self.server_id, command, user)
                if not success:
                    await self.send(
                        json.dumps(
                            {
                                "type": "error",
                                "message": "Failed to send command. Server may not be running.",
                            }
                        )
                    )

        elif message_type == "action":
            action = data.get("action")
            if action == "start":
                await self.start_server(self.server_id)
            elif action == "stop":
                await self.stop_server(self.server_id)
            elif action == "restart":
                await self.restart_server(self.server_id)

    async def server_log(self, event):
        await self.send(json.dumps({"type": "log", "log": event["log"]}))

    async def server_status(self, event):
        await self.send(json.dumps({"type": "status", "status": event["status"]}))

    async def server_stats(self, event):
        await self.send(json.dumps({"type": "stats", "stats": event["stats"]}))

    @database_sync_to_async
    def check_server_access(self, user, server_id):
        from .models import MinecraftServer

        try:
            server = MinecraftServer.objects.get(id=server_id)
            return server.owner == user or user.is_staff
        except MinecraftServer.DoesNotExist:
            return False

    @database_sync_to_async
    def get_recent_logs(self, server_id, limit=100):
        from .models import ServerLog

        logs = ServerLog.objects.filter(server_id=server_id).order_by("-timestamp")[
            :limit
        ]

        return [
            {
                "id": log.id,
                "level": log.level,
                "message": log.message,
                "timestamp": log.timestamp.isoformat(),
            }
            for log in reversed(list(logs))
        ]

    @database_sync_to_async
    def get_server_status(self, server_id):
        from .models import MinecraftServer
        from .server_manager import MinecraftServerManager

        try:
            server = MinecraftServer.objects.get(id=server_id)
            return MinecraftServerManager.get_server_status(server)
        except MinecraftServer.DoesNotExist:
            return None

    @database_sync_to_async
    def send_server_command(self, server_id, command, user):
        from .models import MinecraftServer
        from .server_manager import MinecraftServerManager

        try:
            server = MinecraftServer.objects.get(id=server_id)
            MinecraftServerManager.send_command(server, command, user)
            return True
        except Exception as e:
            print(f"Command error: {e}")
            return False

    @database_sync_to_async
    def start_server(self, server_id):
        from .models import MinecraftServer
        from .server_manager import MinecraftServerManager

        try:
            server = MinecraftServer.objects.get(id=server_id)
            MinecraftServerManager.start_server(server)
        except Exception as e:
            print(f"Start error: {e}")

    @database_sync_to_async
    def stop_server(self, server_id):
        from .models import MinecraftServer
        from .server_manager import MinecraftServerManager

        try:
            server = MinecraftServer.objects.get(id=server_id)
            MinecraftServerManager.stop_server(server)
        except Exception as e:
            print(f"Stop error: {e}")

    @database_sync_to_async
    def restart_server(self, server_id):
        from .models import MinecraftServer
        from .server_manager import MinecraftServerManager

        try:
            server = MinecraftServer.objects.get(id=server_id)
            MinecraftServerManager.restart_server(server)
        except Exception as e:
            print(f"Restart error: {e}")
