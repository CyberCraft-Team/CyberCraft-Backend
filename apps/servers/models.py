from django.db import models
from django.conf import settings
import hashlib
import os
import uuid


class Modpack(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    version = models.CharField(max_length=20)
    minecraft_version = models.CharField(max_length=20)
    forge_version = models.CharField(max_length=50, blank=True, null=True)
    fabric_version = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "modpacks"
        verbose_name = "Modpack"
        verbose_name_plural = "Modpacks"

    def __str__(self):
        return f"{self.name} v{self.version}"


class ModpackFile(models.Model):
    class FileType(models.TextChoices):
        MOD = "mod", "Mod"
        CONFIG = "config", "Config"
        RESOURCE = "resource", "Resource Pack"
        SHADER = "shader", "Shader"
        OTHER = "other", "Other"

    modpack = models.ForeignKey(Modpack, on_delete=models.CASCADE, related_name="files")
    file_type = models.CharField(
        max_length=20, choices=FileType.choices, default=FileType.MOD
    )
    relative_path = models.CharField(max_length=500)
    file = models.FileField(upload_to="modpack_files/")
    sha256_hash = models.CharField(max_length=64)
    file_size = models.BigIntegerField(default=0)
    is_required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "modpack_files"
        verbose_name = "Modpack File"
        verbose_name_plural = "Modpack Files"
        unique_together = ["modpack", "relative_path"]

    def save(self, *args, **kwargs):
        if self.file and not self.sha256_hash:
            self.sha256_hash = self.calculate_hash()
            self.file_size = self.file.size
        super().save(*args, **kwargs)

    def calculate_hash(self):
        sha256 = hashlib.sha256()
        for chunk in self.file.chunks():
            sha256.update(chunk)
        return sha256.hexdigest()

    def __str__(self):
        return f"{self.modpack.name} - {self.relative_path}"


class ServerTypeConfig(models.Model):
    class ServerTypeChoices(models.TextChoices):
        VANILLA = "vanilla", "Vanilla"
        PAPER = "paper", "Paper"
        SPIGOT = "spigot", "Spigot"
        FORGE = "forge", "Forge"
        FABRIC = "fabric", "Fabric"
        PURPUR = "purpur", "Purpur"
        NEOFORGE = "neoforge", "NeoForge"
        CUSTOM = "custom", "Custom"

    server_type = models.CharField(
        max_length=20, choices=ServerTypeChoices.choices, unique=True, primary_key=True
    )
    display_name = models.CharField(max_length=50)
    description = models.TextField(blank=True)

    is_installer = models.BooleanField(
        default=False,
        help_text="Agar True bo'lsa, JAR fayl installer hisoblanadi va avval install qilinadi",
    )

    install_command = models.TextField(
        blank=True,
        help_text="Installer uchun command. O'zgaruvchilar: {java}, {min_ram}, {max_ram}, {jar_file}",
    )

    run_command = models.TextField(
        help_text="Serverni ishga tushirish command. O'zgaruvchilar: {java}, {min_ram}, {max_ram}, {jar_file}"
    )

    requires_args_file = models.BooleanField(
        default=False,
        help_text="Agar True bo'lsa, @libraries/... args fayl ishlatiladi",
    )
    args_file_pattern = models.CharField(
        max_length=255,
        blank=True,
        help_text="Args fayl pattern (masalan: libraries/net/minecraftforge/forge/*/unix_args.txt)",
    )

    jar_file_name = models.CharField(
        max_length=100,
        default="server.jar",
        help_text="JAR fayl server papkasida qanday nomda saqlanadi",
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "server_type_configs"
        verbose_name = "Server Type Config"
        verbose_name_plural = "Server Type Configs"
        ordering = ["display_name"]

    def __str__(self):
        return self.display_name

    def _command_context(self, server):
        """Placeholders available to install_command and run_command.

        Templates are admin-editable, so a typo here surfaces as a KeyError
        deep inside a subprocess launch. _format below turns that into a
        message naming the bad placeholder and the valid ones.
        """
        return {
            "java": "java",
            "min_ram": server.min_ram,
            "max_ram": server.max_ram,
            "jar_file": self.jar_file_name,
            "mc_version": server.minecraft_version,
            "loader_version": server.loader_version or "",
        }

    def _format(self, template, server, field_name):
        context = self._command_context(server)
        try:
            return template.format(**context)
        except KeyError as exc:
            raise ValueError(
                f"{field_name} for server type '{self.server_type}' references "
                f"unknown placeholder {exc}. Available: "
                f"{', '.join('{' + k + '}' for k in sorted(context))}"
            ) from exc

    def get_install_command(self, server):
        if not self.install_command:
            return None
        return self._format(self.install_command, server, "install_command")

    def get_run_command(self, server):
        return self._format(self.run_command, server, "run_command")


class ServerJar(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=200, help_text="JAR fayl nomi (masalan: Paper 1.20.4)"
    )
    server_type = models.ForeignKey(
        ServerTypeConfig,
        on_delete=models.PROTECT,
        related_name="jars",
        help_text="Server turi konfiguratsiyasi",
    )
    minecraft_version = models.CharField(max_length=20)
    jar_file = models.FileField(upload_to="server_jars/")
    file_name = models.CharField(max_length=255)
    file_size = models.BigIntegerField(default=0)
    sha256_hash = models.CharField(max_length=64, blank=True)
    description = models.TextField(
        blank=True, help_text="JAR fayl haqida qo'shimcha ma'lumot"
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_jars",
    )
    is_active = models.BooleanField(
        default=True, help_text="Aktiv JAR fayllar server yaratishda ko'rinadi"
    )
    is_default = models.BooleanField(default=False, help_text="Default JAR fayl")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "server_jars"
        verbose_name = "Server JAR"
        verbose_name_plural = "Server JARs"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.jar_file:
            if not self.sha256_hash:
                sha256 = hashlib.sha256()
                for chunk in self.jar_file.chunks():
                    sha256.update(chunk)
                self.sha256_hash = sha256.hexdigest()
            self.file_size = self.jar_file.size
            if not self.file_name:
                self.file_name = os.path.basename(self.jar_file.name)

        if self.is_default:
            ServerJar.objects.filter(
                server_type=self.server_type,
                minecraft_version=self.minecraft_version,
                is_default=True,
            ).exclude(pk=self.pk).update(is_default=False)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.server_type} {self.minecraft_version})"


class MinecraftServer(models.Model):
    class Status(models.TextChoices):
        STOPPED = "stopped", "Stopped"
        STARTING = "starting", "Starting"
        RUNNING = "running", "Running"
        STOPPING = "stopping", "Stopping"
        INSTALLING = "installing", "Installing"
        ERROR = "error", "Error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_servers"
    )

    server_type = models.ForeignKey(
        ServerTypeConfig,
        on_delete=models.PROTECT,
        related_name="servers",
        null=True,
        blank=True,
    )
    minecraft_version = models.CharField(max_length=20, default="1.20.4")
    loader_version = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Forge/Fabric/NeoForge versiyasi (masalan: 47.2.0)",
    )

    server_jar = models.ForeignKey(
        ServerJar,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="servers",
        help_text="Admin tomonidan yuklangan JAR fayl",
    )
    jar_file = models.CharField(max_length=255, blank=True)

    is_installed = models.BooleanField(
        default=False,
        help_text="Installer turlari uchun - install jarayoni tugaganligini ko'rsatadi",
    )

    port = models.IntegerField(default=25565, unique=True)

    min_ram = models.IntegerField(default=1024, help_text="Minimum RAM in MB")
    max_ram = models.IntegerField(default=2048, help_text="Maximum RAM in MB")

    max_players = models.IntegerField(default=20)
    motd = models.CharField(max_length=200, default="A CyberCraft Minecraft Server")
    gamemode = models.CharField(max_length=20, default="survival")
    difficulty = models.CharField(max_length=20, default="normal")
    pvp = models.BooleanField(default=True)
    online_mode = models.BooleanField(default=False)
    white_list = models.BooleanField(default=False)
    spawn_protection = models.IntegerField(default=16)
    view_distance = models.IntegerField(default=10)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.STOPPED
    )
    current_players = models.IntegerField(default=0)
    pid = models.IntegerField(null=True, blank=True)

    icon = models.ImageField(upload_to="server_icons/", blank=True, null=True)
    background_image = models.ImageField(
        upload_to="server_backgrounds/",
        blank=True,
        null=True,
        help_text="Orqa fon rasmi launcher hero sectionida ko'rinadi",
    )

    server_path = models.CharField(max_length=500, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_started = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "servers_minecraftserver"
        verbose_name = "Minecraft Server"
        verbose_name_plural = "Minecraft Servers"

    def __str__(self):
        return f"{self.name} ({self.server_type} {self.minecraft_version})"

    def get_server_directory(self):
        return os.path.join(settings.SERVERS_ROOT, str(self.id))


class ServerMod(models.Model):
    class ModStatus(models.TextChoices):
        ENABLED = "enabled", "Enabled"
        DISABLED = "disabled", "Disabled"

    server = models.ForeignKey(
        MinecraftServer, on_delete=models.CASCADE, related_name="mods"
    )
    name = models.CharField(max_length=200)
    file_name = models.CharField(max_length=255)
    file = models.FileField(upload_to="server_mods/")
    version = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    sha256_hash = models.CharField(max_length=64, blank=True)
    file_size = models.BigIntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=ModStatus.choices, default=ModStatus.ENABLED
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "server_mods"
        unique_together = ["server", "file_name"]

    def save(self, *args, **kwargs):
        if self.file:
            if not self.sha256_hash:
                sha256 = hashlib.sha256()
                for chunk in self.file.chunks():
                    sha256.update(chunk)
                self.sha256_hash = sha256.hexdigest()
            self.file_size = self.file.size
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.server.name})"


class ServerLog(models.Model):
    class LogLevel(models.TextChoices):
        INFO = "info", "Info"
        WARN = "warn", "Warning"
        ERROR = "error", "Error"
        DEBUG = "debug", "Debug"

    server = models.ForeignKey(
        MinecraftServer, on_delete=models.CASCADE, related_name="logs"
    )
    level = models.CharField(
        max_length=10, choices=LogLevel.choices, default=LogLevel.INFO
    )
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "server_logs"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"[{self.level}] {self.message[:50]}"


class ServerCommand(models.Model):
    server = models.ForeignKey(
        MinecraftServer, on_delete=models.CASCADE, related_name="commands"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    command = models.CharField(max_length=500)
    executed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "server_commands"
        ordering = ["-executed_at"]


class Server(models.Model):
    class Status(models.TextChoices):
        ONLINE = "online", "Online"
        OFFLINE = "offline", "Offline"
        MAINTENANCE = "maintenance", "Maintenance"

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    ip_address = models.CharField(max_length=100)
    port = models.IntegerField(default=25565)
    modpack = models.ForeignKey(
        Modpack, on_delete=models.SET_NULL, null=True, related_name="servers"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OFFLINE
    )
    max_players = models.IntegerField(default=20)
    current_players = models.IntegerField(default=0)
    description = models.TextField(blank=True)
    icon = models.ImageField(upload_to="server_icons/", blank=True, null=True)
    background_image = models.ImageField(
        upload_to="server_backgrounds/",
        blank=True,
        null=True,
        help_text="Orqa fon rasmi launcher hero sectionida ko'rinadi",
    )
    category = models.CharField(
        max_length=50,
        blank=True,
        default="Survival",
        help_text="Server kategoriyasi (masalan: Survival, Creative, Unique)",
    )
    last_wipe = models.DateField(
        null=True,
        blank=True,
        help_text="Oxirgi wipe sanasi",
    )
    whitelist_enabled = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    min_ram = models.IntegerField(default=2048, help_text="Minimum RAM in MB")
    max_ram = models.IntegerField(default=4096, help_text="Maximum RAM in MB")
    java_args = models.TextField(blank=True, help_text="Additional JVM arguments")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "servers"
        verbose_name = "Server"
        verbose_name_plural = "Servers"

    def __str__(self):
        return self.name


class ServerGalleryImage(models.Model):
    server = models.ForeignKey(
        Server, on_delete=models.CASCADE, related_name="gallery_images"
    )
    image = models.ImageField(upload_to="server_gallery/")
    caption = models.CharField(max_length=200, blank=True)
    order = models.IntegerField(default=0, help_text="Tartib raqami (kichik = birinchi)")

    class Meta:
        db_table = "server_gallery_images"
        ordering = ["order", "id"]
        verbose_name = "Server Gallery Image"
        verbose_name_plural = "Server Gallery Images"

    def __str__(self):
        return f"{self.server.name} - Image #{self.order}"


class MinecraftServerGalleryImage(models.Model):
    server = models.ForeignKey(
        MinecraftServer, on_delete=models.CASCADE, related_name="gallery_images"
    )
    image = models.ImageField(upload_to="server_gallery/")
    caption = models.CharField(max_length=200, blank=True)
    order = models.IntegerField(default=0, help_text="Tartib raqami (kichik = birinchi)")

    class Meta:
        db_table = "minecraft_server_gallery_images"
        ordering = ["order", "id"]
        verbose_name = "Minecraft Server Gallery Image"
        verbose_name_plural = "Minecraft Server Gallery Images"

    def __str__(self):
        return f"{self.server.name} - Image #{self.order}"


class ServerFeature(models.Model):
    server = models.ForeignKey(
        Server, on_delete=models.CASCADE, related_name="features"
    )
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    icon = models.CharField(
        max_length=50,
        blank=True,
        default="puzzle",
        help_text="Ikonka nomi (masalan: sword, shield, puzzle, gem, star)",
    )
    order = models.IntegerField(default=0)

    class Meta:
        db_table = "server_features"
        ordering = ["order", "id"]
        verbose_name = "Server Feature"
        verbose_name_plural = "Server Features"

    def __str__(self):
        return f"{self.server.name} - {self.title}"


class SocialLink(models.Model):
    class Platform(models.TextChoices):
        YOUTUBE = "youtube", "YouTube"
        TELEGRAM = "telegram", "Telegram"
        DISCORD = "discord", "Discord"
        INSTAGRAM = "instagram", "Instagram"
        TIKTOK = "tiktok", "TikTok"
        TWITTER = "twitter", "Twitter/X"
        OTHER = "other", "Boshqa"

    platform = models.CharField(max_length=20, choices=Platform.choices)
    name = models.CharField(max_length=100, help_text="Ko'rsatiladigan nom")
    url = models.URLField(help_text="Havola URL manzili")
    icon = models.CharField(
        max_length=50, blank=True, help_text="Lucide icon nomi (masalan: youtube, send)"
    )
    color = models.CharField(
        max_length=100,
        blank=True,
        help_text="Hover rangi CSS classi",
    )
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(
        default=0, help_text="Tartib raqami (kichik = birinchi)"
    )

    class Meta:
        db_table = "social_links"
        ordering = ["order", "id"]
        verbose_name = "Social Link"
        verbose_name_plural = "Social Links"

    def __str__(self):
        return f"{self.name} ({self.platform})"
