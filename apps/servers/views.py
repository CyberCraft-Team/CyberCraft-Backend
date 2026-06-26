from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.parsers import JSONParser
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework import status
from django.db.models import Sum
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from .models import (
    Server,
    MinecraftServer,
    ServerMod,
    ServerLog,
    ServerJar,
    ServerTypeConfig,
    SocialLink,
    MinecraftServerGalleryImage,
)
from .serializers import (
    ServerListSerializer,
    MinecraftServerListSerializer,
    MinecraftServerDetailSerializer,
    MinecraftServerCreateSerializer,
    ServerModSerializer,
    ServerLogSerializer,
    ServerJarSerializer,
    ServerJarUploadSerializer,
    ServerJarListSerializer,
    ServerTypeConfigSerializer,
    ServerTypeConfigDetailSerializer,
    SocialLinkSerializer,
    MinecraftServerGalleryImageSerializer,
)
from .server_manager import MinecraftServerManager

User = get_user_model()


class PublicServersView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        all_servers = []

        servers = Server.objects.filter(is_active=True).select_related("modpack")
        serializer = ServerListSerializer(
            servers, many=True, context={"request": request}
        )
        all_servers.extend(serializer.data)

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

            all_servers.append(
                {
                    "id": server.id,
                    "name": server.name,
                    "slug": server.slug,
                    "ip_address": server_ip,
                    "port": server.port,
                    "status": display_status,
                    "current_players": server.current_players,
                    "max_players": server.max_players,
                    "description": server.motd,
                    "icon_url": None,
                    "minecraft_version": server.minecraft_version,
                    "server_type": (
                        server.server_type.server_type
                        if server.server_type
                        else "vanilla"
                    ),
                    "is_managed": True,
                }
            )

        return Response(all_servers)


class PublicStatsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        servers = Server.objects.filter(is_active=True)
        online_players = (
            servers.filter(status="online").aggregate(total=Sum("current_players"))[
                "total"
            ]
            or 0
        )
        max_online = servers.aggregate(total=Sum("max_players"))["total"] or 0
        total_registered = User.objects.count()
        active_servers = servers.filter(status="online").count()

        return Response(
            {
                "online_players": online_players,
                "max_online": max_online,
                "total_registered": total_registered,
                "active_servers": active_servers,
            }
        )


class MinecraftVersionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        versions = (
            ServerJar.objects.filter(is_active=True)
            .values_list("minecraft_version", flat=True)
            .distinct()
            .order_by("-minecraft_version")
        )

        if not versions:
            return Response(
                [
                    {"id": "1.21", "type": "release"},
                    {"id": "1.20.4", "type": "release"},
                    {"id": "1.20.1", "type": "release"},
                ]
            )

        return Response([{"id": v, "type": "release"} for v in versions])


class MinecraftServerListView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        # Admin barcha serverlarni ko'radi, oddiy foydalanuvchi faqat o'zinikini
        if request.user.is_staff:
            servers = MinecraftServer.objects.all().order_by("-created_at")
        else:
            servers = MinecraftServer.objects.filter(owner=request.user).order_by("-created_at")
        serializer = MinecraftServerListSerializer(servers, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = MinecraftServerCreateSerializer(data=request.data)
        if serializer.is_valid():
            server = None
            try:
                server = serializer.save(owner=request.user)
                uploaded_zip = getattr(server, "_uploaded_zip_file", None)
                if uploaded_zip:
                    MinecraftServerManager.setup_server_from_zip(server, uploaded_zip)
                else:
                    MinecraftServerManager.setup_server_from_jar(server)
                return Response(
                    MinecraftServerDetailSerializer(server, context={"request": request}).data,
                    status=status.HTTP_201_CREATED,
                )
            except Exception as e:
                if server:
                    try:
                        MinecraftServerManager.delete_server(server)
                    except Exception:
                        pass
                return Response(
                    {"error": f"Server yaratishda xato: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MinecraftServerDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_server(self, request, server_id):
        server = get_object_or_404(MinecraftServer, id=server_id)
        if server.owner != request.user and not request.user.is_staff:
            return None
        return server

    def get(self, request, server_id):
        server = self.get_server(request, server_id)
        if not server:
            return Response({"error": "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)
        serializer = MinecraftServerDetailSerializer(server, context={"request": request})
        data = serializer.data
        data["status_info"] = MinecraftServerManager.get_server_status(server)
        return Response(data)

    def patch(self, request, server_id):
        server = self.get_server(request, server_id)
        if not server:
            return Response({"error": "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)
        serializer = MinecraftServerCreateSerializer(
            server, data=request.data, partial=True
        )
        if serializer.is_valid():
            server = serializer.save()
            if server.status == MinecraftServer.Status.STOPPED:
                MinecraftServerManager.create_server_properties(server)
            return Response(
                MinecraftServerDetailSerializer(server, context={"request": request}).data
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, server_id):
        server = self.get_server(request, server_id)
        if not server:
            return Response({"error": "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)
        MinecraftServerManager.delete_server(server)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MinecraftServerControlView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, server_id, action):
        server = get_object_or_404(MinecraftServer, id=server_id)
        if server.owner != request.user and not request.user.is_staff:
            return Response({"error": "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)

        try:
            actions = {
                "start": (
                    MinecraftServerManager.start_server,
                    "Server ishga tushirilmoqda",
                ),
                "stop": (MinecraftServerManager.stop_server, "Server to'xtatilmoqda"),
                "restart": (
                    MinecraftServerManager.restart_server,
                    "Server qayta ishga tushirilmoqda",
                ),
                "kill": (
                    lambda s: MinecraftServerManager.stop_server(s, force=True),
                    "Server majburiy to'xtatildi",
                ),
                "install": (
                    MinecraftServerManager.install_server,
                    "Server install qilinmoqda",
                ),
            }

            if action not in actions:
                return Response(
                    {"error": "Noto'g'ri action"}, status=status.HTTP_400_BAD_REQUEST
                )

            func, message = actions[action]
            func(server)
            return Response({"message": message})

        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MinecraftServerCommandView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, server_id):
        server = get_object_or_404(MinecraftServer, id=server_id)
        if server.owner != request.user and not request.user.is_staff:
            return Response({"error": "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)

        command = request.data.get("command", "").strip()
        if not command:
            return Response(
                {"error": "Command kiritilmagan"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            MinecraftServerManager.send_command(server, command, request.user)
            return Response({"message": "Command yuborildi"})
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MinecraftServerLogsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, server_id):
        server = get_object_or_404(MinecraftServer, id=server_id)
        if server.owner != request.user and not request.user.is_staff:
            return Response({"error": "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)

        limit = int(request.query_params.get("limit", 100))
        since_id = request.query_params.get("since_id")

        logs_query = ServerLog.objects.filter(server=server)

        if since_id:
            logs_query = logs_query.filter(id__gt=int(since_id))

        logs = logs_query.order_by("-timestamp")[:limit]
        logs = list(reversed(list(logs)))

        serializer = ServerLogSerializer(logs, many=True)
        return Response(serializer.data)


class MinecraftServerModsView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_server(self, request, server_id):
        server = get_object_or_404(MinecraftServer, id=server_id)
        if server.owner != request.user and not request.user.is_staff:
            return None
        return server

    def get(self, request, server_id):
        server = self.get_server(request, server_id)
        if not server:
            return Response({"error": "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)
        mods = server.mods.all()
        serializer = ServerModSerializer(mods, many=True)
        return Response(serializer.data)

    def post(self, request, server_id):
        server = self.get_server(request, server_id)
        if not server:
            return Response({"error": "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)

        mod_file = request.FILES.get("file")
        if not mod_file:
            return Response(
                {"error": "Fayl yuklanmagan"}, status=status.HTTP_400_BAD_REQUEST
            )
        if not mod_file.name.endswith(".jar"):
            return Response(
                {"error": "Faqat .jar fayllar qabul qilinadi"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            MinecraftServerManager.install_mod(server, mod_file, mod_file.name)
            mod = ServerMod.objects.create(
                server=server,
                name=request.data.get("name", mod_file.name.replace(".jar", "")),
                file_name=mod_file.name,
                file=mod_file,
                version=request.data.get("version", ""),
                description=request.data.get("description", ""),
            )
            return Response(
                ServerModSerializer(mod).data, status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MinecraftServerModDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_server_and_mod(self, request, server_id, mod_id):
        server = get_object_or_404(MinecraftServer, id=server_id)
        if server.owner != request.user and not request.user.is_staff:
            return None, None
        mod = get_object_or_404(ServerMod, id=mod_id, server=server)
        return server, mod

    def patch(self, request, server_id, mod_id):
        server, mod = self.get_server_and_mod(request, server_id, mod_id)
        if not server:
            return Response({"error": "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)

        new_status = request.data.get("status")
        if new_status not in ["enabled", "disabled"]:
            return Response(
                {"error": "Noto'g'ri status"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            MinecraftServerManager.toggle_mod(
                server, mod.file_name, enable=(new_status == "enabled")
            )
            mod.status = new_status
            mod.save()
            return Response(ServerModSerializer(mod).data)
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def delete(self, request, server_id, mod_id):
        server, mod = self.get_server_and_mod(request, server_id, mod_id)
        if not server:
            return Response({"error": "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)

        try:
            MinecraftServerManager.remove_mod(server, mod.file_name)
            mod.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MinecraftServerFilesView(APIView):
    permission_classes = [IsAuthenticated]

    def get_server(self, request, server_id):
        server = get_object_or_404(MinecraftServer, id=server_id)
        if server.owner != request.user and not request.user.is_staff:
            return None
        return server

    def get(self, request, server_id):
        server = self.get_server(request, server_id)
        if not server:
            return Response({"error": "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)

        path = request.query_params.get("path", "")
        if request.query_params.get("content") == "true":
            try:
                content = MinecraftServerManager.read_file(server, path)
                return Response({"content": content})
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        files = MinecraftServerManager.get_server_files(server, path)
        return Response(files)

    def post(self, request, server_id):
        server = self.get_server(request, server_id)
        if not server:
            return Response({"error": "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)

        path = request.data.get("path")
        content = request.data.get("content")
        if not path:
            return Response(
                {"error": "Path kiritilmagan"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            MinecraftServerManager.write_file(server, path, content)
            return Response({"message": "Fayl saqlandi"})
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MinecraftServerPlayersView(APIView):
    permission_classes = [IsAuthenticated]

    def get_server(self, request, server_id):
        server = get_object_or_404(MinecraftServer, id=server_id)
        if server.owner != request.user and not request.user.is_staff:
            return None
        return server

    def get(self, request, server_id):
        server = self.get_server(request, server_id)
        if not server:
            return Response({"error": "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)

        lists = MinecraftServerManager.get_player_lists(server)
        return Response(lists)

    def post(self, request, server_id):
        server = self.get_server(request, server_id)
        if not server:
            return Response({"error": "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)

        list_type = request.data.get("list_type")
        action = request.data.get("action")
        username = request.data.get("username", "").strip()
        reason = request.data.get("reason", "Banned by admin")

        if not list_type or not action or not username:
            return Response(
                {"error": "list_type, action va username bo'lishi shart"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            MinecraftServerManager.modify_player_list(
                server, list_type, action, username, reason
            )
            return Response({"message": "Muvaffaqiyatli bajarildi"})
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ServerJarListView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        server_type = request.query_params.get("server_type")
        minecraft_version = request.query_params.get("minecraft_version")
        active_only = request.query_params.get("active_only", "true").lower() == "true"

        queryset = ServerJar.objects.all()
        if active_only:
            queryset = queryset.filter(is_active=True)
        if server_type:
            queryset = queryset.filter(server_type=server_type)
        if minecraft_version:
            queryset = queryset.filter(minecraft_version=minecraft_version)

        if request.user.is_staff:
            serializer = ServerJarSerializer(
                queryset, many=True, context={"request": request}
            )
        else:
            serializer = ServerJarListSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not request.user.is_staff:
            return Response(
                {"error": "Faqat adminlar JAR yuklashi mumkin"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ServerJarUploadSerializer(data=request.data)
        if serializer.is_valid():
            jar = serializer.save(uploaded_by=request.user)
            return Response(
                ServerJarSerializer(jar, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ServerJarDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, jar_id):
        jar = get_object_or_404(ServerJar, id=jar_id)
        serializer = ServerJarSerializer(jar, context={"request": request})
        return Response(serializer.data)

    def patch(self, request, jar_id):
        if not request.user.is_staff:
            return Response(
                {"error": "Faqat adminlar"}, status=status.HTTP_403_FORBIDDEN
            )

        jar = get_object_or_404(ServerJar, id=jar_id)
        for field in ["name", "description", "is_active", "is_default"]:
            if field in request.data:
                setattr(jar, field, request.data[field])
        jar.save()
        return Response(ServerJarSerializer(jar, context={"request": request}).data)

    def delete(self, request, jar_id):
        if not request.user.is_staff:
            return Response(
                {"error": "Faqat adminlar"}, status=status.HTTP_403_FORBIDDEN
            )

        jar = get_object_or_404(ServerJar, id=jar_id)
        if jar.servers.exists():
            return Response(
                {"error": "Bu JAR faylga bog'langan serverlar mavjud"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        jar.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ServerJarVersionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        server_type = request.query_params.get("server_type")
        queryset = ServerJar.objects.filter(is_active=True)
        if server_type:
            queryset = queryset.filter(server_type=server_type)

        versions = (
            queryset.values_list("minecraft_version", flat=True)
            .distinct()
            .order_by("-minecraft_version")
        )
        return Response([{"id": v, "type": "release"} for v in versions])


class ServerTypeConfigListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        active_only = request.query_params.get("active_only", "true").lower() == "true"
        if active_only:
            configs = ServerTypeConfig.objects.filter(is_active=True)
        else:
            configs = ServerTypeConfig.objects.all()
        serializer = ServerTypeConfigSerializer(configs, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not request.user.is_staff:
            return Response(
                {"error": "Faqat adminlar"}, status=status.HTTP_403_FORBIDDEN
            )

        serializer = ServerTypeConfigDetailSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ServerTypeConfigDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, server_type):
        config = get_object_or_404(ServerTypeConfig, server_type=server_type)
        if request.user.is_staff:
            serializer = ServerTypeConfigDetailSerializer(config)
        else:
            serializer = ServerTypeConfigSerializer(config)
        return Response(serializer.data)

    def patch(self, request, server_type):
        if not request.user.is_staff:
            return Response(
                {"error": "Faqat adminlar"}, status=status.HTTP_403_FORBIDDEN
            )

        config = get_object_or_404(ServerTypeConfig, server_type=server_type)
        serializer = ServerTypeConfigDetailSerializer(
            config, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, server_type):
        if not request.user.is_staff:
            return Response(
                {"error": "Faqat adminlar"}, status=status.HTTP_403_FORBIDDEN
            )

        config = get_object_or_404(ServerTypeConfig, server_type=server_type)
        if config.servers.exists() or config.jars.exists():
            return Response(
                {"error": "Bu turga bog'langan serverlar yoki JAR fayllar mavjud"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        config.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminServersListCreateView(ListCreateAPIView):
    permission_classes = [IsAdminUser]
    queryset = Server.objects.all().select_related("modpack").order_by("-created_at")
    serializer_class = ServerListSerializer

    def perform_create(self, serializer):
        serializer.save()


class AdminServerDetailView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    queryset = Server.objects.all().select_related("modpack")
    serializer_class = ServerListSerializer


class PublicSocialLinksView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        links = SocialLink.objects.filter(is_active=True)
        serializer = SocialLinkSerializer(links, many=True)
        return Response(serializer.data)


class AdminSocialLinksView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        links = SocialLink.objects.all()
        serializer = SocialLinkSerializer(links, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = SocialLinkSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminSocialLinkDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        link = get_object_or_404(SocialLink, pk=pk)
        serializer = SocialLinkSerializer(link, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        link = get_object_or_404(SocialLink, pk=pk)
        link.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class MinecraftServerImageUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def patch(self, request, server_id):
        server = get_object_or_404(MinecraftServer, id=server_id)
        if server.owner != request.user and not request.user.is_staff:
            return Response({"error": "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)

        if "icon" in request.FILES:
            server.icon = request.FILES["icon"]
        if "background_image" in request.FILES:
            server.background_image = request.FILES["background_image"]

        server.save()
        serializer = MinecraftServerDetailSerializer(server, context={"request": request})
        return Response(serializer.data)


class MinecraftServerGalleryUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, server_id):
        server = get_object_or_404(MinecraftServer, id=server_id)
        if server.owner != request.user and not request.user.is_staff:
            return Response({"error": "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)

        image = request.FILES.get("image")
        if not image:
            return Response(
                {"error": "Rasm yuklanmagan"}, status=status.HTTP_400_BAD_REQUEST
            )

        gallery_img = MinecraftServerGalleryImage.objects.create(
            server=server,
            image=image,
            caption=request.data.get("caption", ""),
            order=request.data.get("order", 0),
        )

        serializer = MinecraftServerGalleryImageSerializer(
            gallery_img, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def delete(self, request, server_id, image_id):
        server = get_object_or_404(MinecraftServer, id=server_id)
        if server.owner != request.user and not request.user.is_staff:
            return Response({"error": "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)

        image = get_object_or_404(
            MinecraftServerGalleryImage, id=image_id, server=server
        )
        image.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
