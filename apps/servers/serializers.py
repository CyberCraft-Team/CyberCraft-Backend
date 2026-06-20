from django.conf import settings
from rest_framework import serializers
from .models import (
    Modpack,
    ModpackFile,
    Server,
    MinecraftServer,
    ServerMod,
    ServerLog,
    ServerJar,
    ServerTypeConfig,
    SocialLink,
    ServerGalleryImage,
    ServerFeature,
    MinecraftServerGalleryImage
)


class ModpackFileSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ModpackFile
        fields = [
            "relative_path",
            "file_type",
            "sha256_hash",
            "file_size",
            "url",
            "is_required",
        ]

    def get_url(self, obj):
        request = self.context.get("request")
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None


class ModpackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Modpack
        fields = [
            "id",
            "name",
            "slug",
            "version",
            "minecraft_version",
            "forge_version",
            "fabric_version",
            "description",
        ]


class ServerListSerializer(serializers.ModelSerializer):
    modpack_name = serializers.CharField(source="modpack.name", read_only=True)
    modpack_version = serializers.CharField(source="modpack.version", read_only=True)
    minecraft_version = serializers.CharField(
        source="modpack.minecraft_version", read_only=True
    )
    icon_url = serializers.SerializerMethodField()
    background_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Server
        fields = [
            "id",
            "name",
            "slug",
            "ip_address",
            "port",
            "status",
            "current_players",
            "max_players",
            "description",
            "icon_url",
            "background_image_url",
            "modpack_name",
            "modpack_version",
            "minecraft_version",
            "whitelist_enabled",
            "min_ram",
            "max_ram",
        ]

    def get_icon_url(self, obj):
        request = self.context.get("request")
        if obj.icon and request:
            return request.build_absolute_uri(obj.icon.url)
        return None

    def get_background_image_url(self, obj):
        request = self.context.get("request")
        if obj.background_image and request:
            return request.build_absolute_uri(obj.background_image.url)
        return None


class ServerGalleryImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ServerGalleryImage
        fields = ["id", "image_url", "caption", "order"]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


class ServerFeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServerFeature
        fields = ["id", "title", "description", "icon", "order"]


class MinecraftServerGalleryImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = MinecraftServerGalleryImage
        fields = ["id", "image_url", "caption", "order"]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


class ServerModSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServerMod
        fields = [
            "id",
            "name",
            "file_name",
            "version",
            "description",
            "file_size",
            "status",
            "uploaded_at",
        ]
        read_only_fields = ["id", "file_size", "uploaded_at"]


class ServerLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServerLog
        fields = ["id", "level", "message", "timestamp"]


class ServerTypeConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServerTypeConfig
        fields = [
            "server_type",
            "display_name",
            "description",
            "is_installer",
            "jar_file_name",
            "is_active",
        ]


class ServerTypeConfigDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServerTypeConfig
        fields = "__all__"


class ServerJarSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(
        source="uploaded_by.username", read_only=True
    )
    file_url = serializers.SerializerMethodField()
    servers_count = serializers.SerializerMethodField()
    server_type_info = ServerTypeConfigSerializer(source="server_type", read_only=True)

    class Meta:
        model = ServerJar
        fields = [
            "id",
            "name",
            "server_type",
            "server_type_info",
            "minecraft_version",
            "file_name",
            "file_size",
            "sha256_hash",
            "description",
            "uploaded_by",
            "uploaded_by_name",
            "is_active",
            "is_default",
            "file_url",
            "servers_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "file_name",
            "file_size",
            "sha256_hash",
            "uploaded_by",
            "created_at",
            "updated_at",
        ]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.jar_file and request:
            return request.build_absolute_uri(obj.jar_file.url)
        return None

    def get_servers_count(self, obj):
        return obj.servers.count()


class ServerJarUploadSerializer(serializers.ModelSerializer):
    jar_file = serializers.FileField(required=True)
    server_type = serializers.SlugRelatedField(
        slug_field="server_type", queryset=ServerTypeConfig.objects.all()
    )
    is_active = serializers.BooleanField(default=True)

    class Meta:
        model = ServerJar
        fields = [
            "name",
            "server_type",
            "minecraft_version",
            "jar_file",
            "description",
            "is_active",
            "is_default",
        ]

    def validate_server_type(self, value):
        if not value.is_active:
            raise serializers.ValidationError(
                f"'{value.display_name}' server turi hozirda aktiv emas"
            )
        return value

    def validate_jar_file(self, value):
        if not value.name.endswith(".jar"):
            raise serializers.ValidationError("Faqat .jar fayllar qabul qilinadi")
        if value.size > 500 * 1024 * 1024:
            raise serializers.ValidationError(
                "JAR fayl hajmi 500MB dan oshmasligi kerak"
            )
        return value


class ServerJarListSerializer(serializers.ModelSerializer):
    server_type_display = serializers.CharField(
        source="server_type.display_name", read_only=True
    )

    class Meta:
        model = ServerJar
        fields = [
            "id",
            "name",
            "server_type",
            "server_type_display",
            "minecraft_version",
            "file_size",
            "is_default",
        ]


class MinecraftServerListSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.username", read_only=True)
    mods_count = serializers.SerializerMethodField()
    server_jar_name = serializers.CharField(
        source="server_jar.name", read_only=True, allow_null=True
    )
    server_type_display = serializers.SerializerMethodField()

    class Meta:
        model = MinecraftServer
        fields = [
            "id",
            "name",
            "slug",
            "owner_name",
            "server_type",
            "server_type_display",
            "minecraft_version",
            "port",
            "status",
            "current_players",
            "max_players",
            "min_ram",
            "max_ram",
            "mods_count",
            "server_jar",
            "server_jar_name",
            "is_installed",
            "created_at",
            "last_started",
        ]

    def get_mods_count(self, obj):
        return obj.mods.filter(status="enabled").count()

    def get_server_type_display(self, obj):
        if obj.server_type:
            return obj.server_type.display_name
        return "Custom"


class MinecraftServerDetailSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.username", read_only=True)
    mods = ServerModSerializer(many=True, read_only=True)
    server_jar_info = ServerJarListSerializer(
        source="server_jar", read_only=True, allow_null=True
    )
    server_type_info = ServerTypeConfigSerializer(
        source="server_type", read_only=True, allow_null=True
    )
    gallery_images = MinecraftServerGalleryImageSerializer(many=True, read_only=True)
    icon_url = serializers.SerializerMethodField()
    background_image_url = serializers.SerializerMethodField()

    class Meta:
        model = MinecraftServer
        fields = [
            "id",
            "name",
            "slug",
            "owner",
            "owner_name",
            "server_type",
            "server_type_info",
            "minecraft_version",
            "server_jar",
            "server_jar_info",
            "jar_file",
            "port",
            "min_ram",
            "max_ram",
            "max_players",
            "motd",
            "gamemode",
            "difficulty",
            "pvp",
            "online_mode",
            "white_list",
            "spawn_protection",
            "view_distance",
            "status",
            "current_players",
            "pid",
            "server_path",
            "mods",
            "is_installed",
            "icon_url",
            "background_image_url",
            "gallery_images",
            "created_at",
            "updated_at",
            "last_started",
        ]
        read_only_fields = [
            "id",
            "owner",
            "jar_file",
            "server_path",
            "status",
            "current_players",
            "pid",
            "created_at",
            "updated_at",
            "last_started",
        ]

    def get_icon_url(self, obj):
        request = self.context.get("request")
        if obj.icon and request:
            return request.build_absolute_uri(obj.icon.url)
        return None

    def get_background_image_url(self, obj):
        request = self.context.get("request")
        if obj.background_image and request:
            return request.build_absolute_uri(obj.background_image.url)
        return None


class MinecraftServerCreateSerializer(serializers.ModelSerializer):
    server_jar = serializers.UUIDField(required=False, allow_null=True)
    server_zip = serializers.FileField(required=False, allow_null=True, write_only=True)
    server_type = serializers.SlugRelatedField(
        slug_field="server_type",
        queryset=ServerTypeConfig.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = MinecraftServer
        fields = [
            "name",
            "slug",
            "server_jar",
            "server_zip",
            "server_type",
            "minecraft_version",
            "loader_version",
            "port",
            "min_ram",
            "max_ram",
            "max_players",
            "motd",
            "gamemode",
            "difficulty",
            "pvp",
            "online_mode",
            "white_list",
            "spawn_protection",
            "view_distance",
        ]

    def validate_server_jar(self, value):
        if value in [None, ""]:
            return None
        try:
            jar = ServerJar.objects.get(id=value, is_active=True)
            if not jar.jar_file:
                raise serializers.ValidationError("Tanlangan JAR fayl topilmadi")
            return jar
        except ServerJar.DoesNotExist:
            raise serializers.ValidationError(
                f"Bunday JAR fayl topilmadi (ID: {value})"
            )

    def validate_server_zip(self, value):
        if value in [None, ""]:
            return None
        if not value.name.lower().endswith(".zip"):
            raise serializers.ValidationError("Faqat .zip fayllar qabul qilinadi")
        max_bytes = getattr(
            settings, "SERVER_ZIP_MAX_UPLOAD_BYTES", 2 * 1024 * 1024 * 1024
        )
        size = getattr(value, "size", None) or 0
        if size > max_bytes:
            raise serializers.ValidationError(
                f"ZIP hajmi {max_bytes // (1024 * 1024)} MB dan oshmasligi kerak"
            )
        return value

    def validate_name(self, value):
        instance = getattr(self, "instance", None)
        queryset = MinecraftServer.objects.filter(name__iexact=value.strip())
        if instance:
            queryset = queryset.exclude(pk=instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("Bu nomdagi server allaqachon mavjud")
        return value

    def validate_port(self, value):
        instance = getattr(self, "instance", None)
        queryset = MinecraftServer.objects.filter(port=value)
        if instance:
            queryset = queryset.exclude(pk=instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("Bu port allaqachon ishlatilmoqda")
        if value < 1024 or value > 65535:
            raise serializers.ValidationError(
                "Port 1024 va 65535 orasida bo'lishi kerak"
            )
        return value

    def validate_min_ram(self, value):
        if value < 512:
            raise serializers.ValidationError(
                "Minimum RAM kamida 512 MB bo'lishi kerak"
            )
        return value

    def validate_max_ram(self, value):
        if value > 16384:
            raise serializers.ValidationError("Maximum RAM 16 GB dan oshmasligi kerak")
        return value

    def validate(self, data):
        instance = getattr(self, "instance", None)
        is_create = instance is None

        server_jar = data.get("server_jar")
        server_zip = data.get("server_zip")

        if is_create:
            if not server_jar and not server_zip:
                raise serializers.ValidationError(
                    "Server yaratish uchun server_jar yoki server_zip yuborilishi kerak"
                )
            if server_jar and server_zip:
                raise serializers.ValidationError(
                    "Bir vaqtning o'zida faqat bittasini yuboring: server_jar yoki server_zip"
                )
        elif server_jar and server_zip:
            raise serializers.ValidationError(
                "Bir vaqtning o'zida faqat bittasini yuboring: server_jar yoki server_zip"
            )

        min_ram = data.get("min_ram")
        max_ram = data.get("max_ram")
        if instance:
            if min_ram is None:
                min_ram = instance.min_ram
            if max_ram is None:
                max_ram = instance.max_ram
        else:
            if min_ram is None:
                min_ram = 1024
            if max_ram is None:
                max_ram = 2048
        if min_ram > max_ram:
            raise serializers.ValidationError(
                "Minimum RAM maximum RAM dan katta bo'lishi mumkin emas"
            )

        return data

    def create(self, validated_data):
        server_zip = validated_data.pop("server_zip", None)
        server_jar = validated_data.pop("server_jar", None)
        if server_jar:
            validated_data["server_jar"] = server_jar
            validated_data["server_type"] = server_jar.server_type
            validated_data["minecraft_version"] = server_jar.minecraft_version

        if server_jar and server_jar.server_type.server_type in ["forge", "neoforge", "fabric"]:
            import re

            jar_name = server_jar.file_name
            version_match = re.search(r"-(\d+\.\d+\.?\d*)-", jar_name)
            if not version_match:
                version_match = re.search(r"-(\d+\.\d+\.?\d*)\.jar", jar_name)

            if version_match:
                validated_data["loader_version"] = version_match.group(1)

        if server_zip and not validated_data.get("server_type"):
            custom = ServerTypeConfig.objects.filter(
                server_type="custom", is_active=True
            ).first()
            if custom:
                validated_data["server_type"] = custom

        server = super().create(validated_data)
        server._uploaded_zip_file = server_zip
        return server

    def update(self, instance, validated_data):
        validated_data.pop("server_zip", None)
        server_jar = validated_data.pop("server_jar", None)
        if server_jar is not None:
            validated_data["server_jar"] = server_jar
            validated_data["server_type"] = server_jar.server_type
            validated_data["minecraft_version"] = server_jar.minecraft_version
            if server_jar.server_type.server_type in ["forge", "neoforge", "fabric"]:
                import re

                jar_name = server_jar.file_name
                version_match = re.search(r"-(\d+\.\d+\.?\d*)-", jar_name)
                if not version_match:
                    version_match = re.search(r"-(\d+\.\d+\.?\d*)\.jar", jar_name)
                if version_match:
                    validated_data["loader_version"] = version_match.group(1)
        return super().update(instance, validated_data)


class SocialLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialLink
        fields = [
            "id",
            "platform",
            "name",
            "url",
            "icon",
            "color",
            "is_active",
            "order",
        ]
