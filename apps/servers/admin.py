from django.contrib import admin
from .models import (
    Modpack,
    ModpackFile,
    Server,
    ServerJar,
    MinecraftServer,
    ServerTypeConfig,
    SocialLink,
    ServerGalleryImage,
    ServerFeature,
)


class ModpackFileInline(admin.TabularInline):
    model = ModpackFile
    extra = 1
    readonly_fields = ["sha256_hash", "file_size"]


@admin.register(Modpack)
class ModpackAdmin(admin.ModelAdmin):
    list_display = ["name", "version", "minecraft_version", "is_active", "files_count"]
    list_filter = ["is_active", "minecraft_version"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ModpackFileInline]

    def files_count(self, obj):
        return obj.files.count()

    files_count.short_description = "Files"


@admin.register(ModpackFile)
class ModpackFileAdmin(admin.ModelAdmin):
    list_display = [
        "modpack",
        "relative_path",
        "file_type",
        "file_size_display",
        "is_required",
        "is_active",
    ]
    list_filter = ["modpack", "file_type", "is_required", "is_active"]
    search_fields = ["relative_path", "modpack__name"]
    readonly_fields = ["sha256_hash", "file_size"]

    def file_size_display(self, obj):
        if obj.file_size < 1024:
            return f"{obj.file_size} B"
        elif obj.file_size < 1024 * 1024:
            return f"{obj.file_size / 1024:.1f} KB"
        else:
            return f"{obj.file_size / (1024 * 1024):.1f} MB"

    file_size_display.short_description = "Size"


@admin.register(ServerTypeConfig)
class ServerTypeConfigAdmin(admin.ModelAdmin):
    list_display = [
        "server_type",
        "display_name",
        "is_installer",
        "jar_file_name",
        "is_active",
    ]
    list_filter = ["is_installer", "is_active", "requires_args_file"]
    search_fields = ["server_type", "display_name", "description"]

    fieldsets = (
        (None, {"fields": ("server_type", "display_name", "description")}),
        (
            "Installer sozlamalari",
            {
                "fields": ("is_installer", "install_command"),
                "classes": ("collapse",),
            },
        ),
        (
            "Run sozlamalari",
            {
                "fields": ("run_command", "jar_file_name"),
            },
        ),
        (
            "Forge/NeoForge sozlamalari",
            {
                "fields": ("requires_args_file", "args_file_pattern"),
                "classes": ("collapse",),
            },
        ),
        ("Status", {"fields": ("is_active",)}),
    )


@admin.register(ServerJar)
class ServerJarAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "server_type",
        "minecraft_version",
        "file_size_display",
        "is_active",
        "is_default",
        "servers_count",
        "uploaded_by",
        "created_at",
    ]
    list_filter = ["server_type", "minecraft_version", "is_active", "is_default"]
    search_fields = ["name", "file_name", "description"]
    readonly_fields = [
        "sha256_hash",
        "file_size",
        "file_name",
        "created_at",
        "updated_at",
    ]

    fieldsets = (
        (None, {"fields": ("name", "server_type", "minecraft_version")}),
        ("Fayl", {"fields": ("jar_file", "file_name", "file_size", "sha256_hash")}),
        ("Ma'lumot", {"fields": ("description",)}),
        ("Status", {"fields": ("is_active", "is_default", "uploaded_by")}),
        ("Vaqt", {"fields": ("created_at", "updated_at")}),
    )

    def file_size_display(self, obj):
        if obj.file_size < 1024:
            return f"{obj.file_size} B"
        elif obj.file_size < 1024 * 1024:
            return f"{obj.file_size / 1024:.1f} KB"
        else:
            return f"{obj.file_size / (1024 * 1024):.1f} MB"

    file_size_display.short_description = "Hajmi"

    def servers_count(self, obj):
        return obj.servers.count()

    servers_count.short_description = "Serverlar"


@admin.register(MinecraftServer)
class MinecraftServerAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "owner",
        "server_type",
        "minecraft_version",
        "port",
        "status",
        "is_installed",
        "current_players",
        "max_players",
    ]
    list_filter = ["status", "server_type", "minecraft_version", "is_installed"]
    search_fields = ["name", "slug", "owner__username"]
    readonly_fields = [
        "id",
        "server_path",
        "pid",
        "created_at",
        "updated_at",
        "last_started",
    ]


@admin.register(Server)
class ServerAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "ip_address",
        "port",
        "modpack",
        "category",
        "status",
        "current_players",
        "max_players",
        "is_active",
    ]
    list_filter = ["status", "is_active", "whitelist_enabled", "modpack", "category"]
    search_fields = ["name", "slug", "ip_address"]
    prepopulated_fields = {"slug": ("name",)}

    class GalleryInline(admin.TabularInline):
        model = ServerGalleryImage
        extra = 1

    class FeatureInline(admin.TabularInline):
        model = ServerFeature
        extra = 1

    inlines = [GalleryInline, FeatureInline]

    fieldsets = (
        (None, {"fields": ("name", "slug", "description", "category", "icon", "background_image")}),
        ("Connection", {"fields": ("ip_address", "port", "status")}),
        ("Modpack", {"fields": ("modpack",)}),
        (
            "Players",
            {"fields": ("current_players", "max_players", "whitelist_enabled")},
        ),
        ("Java Settings", {"fields": ("min_ram", "max_ram", "java_args")}),
        ("Qo'shimcha", {"fields": ("last_wipe", "is_active")}),
    )


@admin.register(SocialLink)
class SocialLinkAdmin(admin.ModelAdmin):
    list_display = ["name", "platform", "url", "order", "is_active"]
    list_filter = ["platform", "is_active"]
    list_editable = ["order", "is_active"]
    search_fields = ["name", "url"]
    ordering = ["order"]
