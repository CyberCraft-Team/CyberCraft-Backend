from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.servers.models import Server, MinecraftServer
from .authentication import LauncherTokenAuthentication


class LauncherServersView(APIView):
    authentication_classes = [LauncherTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        all_servers = []

        external_servers = Server.objects.filter(is_active=True).select_related(
            "modpack"
        )
        for server in external_servers:
            loader = "vanilla"
            loader_version = None
            if server.modpack:
                if server.modpack.forge_version:
                    loader = "forge"
                    loader_version = server.modpack.forge_version
                elif server.modpack.fabric_version:
                    loader = "fabric"
                    loader_version = server.modpack.fabric_version

            all_servers.append(
                {
                    "id": str(server.id),
                    "uuid": None,
                    "name": server.name,
                    "slug": server.slug,
                    "ip_address": server.ip_address,
                    "port": server.port,
                    "status": server.status,
                    "current_players": server.current_players,
                    "max_players": server.max_players,
                    "description": server.description,
                    "icon_url": (
                        request.build_absolute_uri(server.icon.url)
                        if server.icon
                        else None
                    ),
                    "modpack_id": server.modpack.id if server.modpack else None,
                    "modpack_name": server.modpack.name if server.modpack else None,
                    "modpack_version": (
                        server.modpack.version if server.modpack else None
                    ),
                    "minecraft_version": (
                        server.modpack.minecraft_version if server.modpack else "1.20.4"
                    ),
                    "whitelist_enabled": server.whitelist_enabled,
                    "min_ram": server.min_ram,
                    "max_ram": server.max_ram,
                    "server_type": "external",
                    "is_managed": False,
                    "loader": loader,
                    "loader_version": loader_version,
                }
            )

        managed_servers = MinecraftServer.objects.all().select_related(
            "server_type", "server_jar"
        )

        for server in managed_servers:
            server_ip = request.get_host().split(":")[0]
            if server_ip in ["localhost", "127.0.0.1"]:
                server_ip = "127.0.0.1"

            status_map = {
                "running": "online",
                "starting": "starting",
                "stopping": "stopping",
                "stopped": "offline",
                "installing": "installing",
                "error": "error",
            }
            display_status = status_map.get(server.status, "offline")

            loader = server.server_type.server_type if server.server_type else "vanilla"
            loader_version = server.loader_version

            all_servers.append(
                {
                    "id": str(server.id),
                    "uuid": str(server.id),
                    "name": server.name,
                    "slug": server.slug,
                    "ip_address": server_ip,
                    "port": server.port,
                    "status": display_status,
                    "current_players": server.current_players,
                    "max_players": server.max_players,
                    "description": server.motd,
                    "icon_url": None,
                    "modpack_id": None,
                    "modpack_name": None,
                    "modpack_version": None,
                    "minecraft_version": server.minecraft_version,
                    "whitelist_enabled": server.white_list,
                    "min_ram": server.min_ram,
                    "max_ram": server.max_ram,
                    "server_type": loader,
                    "is_managed": True,
                    "loader": loader,
                    "loader_version": loader_version,
                }
            )

        return Response(all_servers)


class LauncherServerManifestView(APIView):
    authentication_classes = [LauncherTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, server_id):
        try:
            server = MinecraftServer.objects.select_related("server_type").get(
                id=server_id
            )
            return self._get_managed_server_manifest(request, server)
        except (MinecraftServer.DoesNotExist, ValueError):
            pass

        try:
            server_pk = int(server_id)
            server = Server.objects.select_related("modpack").get(
                pk=server_pk, is_active=True
            )
            return self._get_external_server_manifest(request, server)
        except (Server.DoesNotExist, ValueError):
            pass

        return Response({"error": "Server topilmadi"}, status=404)

    def _get_managed_server_manifest(self, request, server):
        server_ip = request.get_host().split(":")[0]
        if server_ip in ["localhost", "127.0.0.1"]:
            server_ip = "127.0.0.1"

        loader = server.server_type.server_type if server.server_type else "vanilla"
        loader_version = server.loader_version

        manifest = {
            "id": str(server.id),
            "name": server.name,
            "address": f"{server_ip}:{server.port}",
            "minecraft": server.minecraft_version,
            "loader": loader,
            "loaderVersion": loader_version,
            "version": "1.0.0",
            "files": {
                "mods": [],
                "resourcepacks": [],
                "shaders": [],
            },
            "forbidden": ["*.jar.disabled", "xray*.jar", "cheat*.jar", "hack*.jar"],
        }

        mods = server.mods.filter(status="enabled")
        for mod in mods:
            manifest["files"]["mods"].append(
                {
                    "name": mod.file_name,
                    "hash": mod.sha256_hash or "",
                    "size": mod.file_size or 0,
                    "required": True,
                    "url": (
                        request.build_absolute_uri(mod.file.url) if mod.file else None
                    ),
                }
            )

        return Response(manifest)

    def _get_external_server_manifest(self, request, server):
        if server.whitelist_enabled and not getattr(
            request.user, "is_whitelisted", False
        ):
            return Response({"error": "Siz whitelist'da emassiz"}, status=403)

        loader = "vanilla"
        loader_version = None

        if server.modpack:
            if server.modpack.forge_version:
                loader = "forge"
                loader_version = server.modpack.forge_version
            elif server.modpack.fabric_version:
                loader = "fabric"
                loader_version = server.modpack.fabric_version

        manifest = {
            "id": str(server.id),
            "name": server.name,
            "address": f"{server.ip_address}:{server.port}",
            "minecraft": (
                server.modpack.minecraft_version if server.modpack else "1.20.4"
            ),
            "loader": loader,
            "loaderVersion": loader_version,
            "version": server.modpack.version if server.modpack else "1.0.0",
            "files": {
                "mods": [],
                "resourcepacks": [],
                "shaders": [],
            },
            "forbidden": ["*.jar.disabled", "xray*.jar", "cheat*.jar", "hack*.jar"],
        }

        if server.modpack:
            files = server.modpack.files.filter(is_active=True)
            for f in files:
                file_data = {
                    "name": f.relative_path.split("/")[-1],
                    "hash": f.sha256_hash or "",
                    "size": f.file_size or 0,
                    "required": f.is_required,
                    "url": (request.build_absolute_uri(f.file.url) if f.file else None),
                }

                if f.file_type == "mod":
                    manifest["files"]["mods"].append(file_data)
                elif f.file_type == "resourcepack":
                    manifest["files"]["resourcepacks"].append(file_data)
                elif f.file_type == "shader":
                    manifest["files"]["shaders"].append(file_data)

        return Response(manifest)


class LauncherUpdateCheckView(APIView):
    """Launcher yangilanishini tekshirish (autentifikatsiyasiz)"""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        client_version = request.query_params.get("version", "")
        platform = request.query_params.get("platform", "win32")

        if not client_version:
            return Response({"error": "version parametri kerak"}, status=400)

        from .models import LauncherVersion

        latest = (
            LauncherVersion.objects.filter(platform=platform, is_active=True)
            .order_by("-created_at")
            .first()
        )

        if not latest:
            return Response({"update_available": False})

        from packaging.version import Version, InvalidVersion

        try:
            client_ver = Version(client_version)
            latest_ver = Version(latest.version)
        except InvalidVersion:
            return Response({"error": "Noto'g'ri versiya formati"}, status=400)

        if latest_ver <= client_ver:
            return Response({"update_available": False})

        download_url = request.build_absolute_uri(latest.download_file.url)

        return Response(
            {
                "update_available": True,
                "version": latest.version,
                "download_url": download_url,
                "release_notes": latest.release_notes,
                "force": latest.force_update,
                "file_size": latest.file_size,
            }
        )
