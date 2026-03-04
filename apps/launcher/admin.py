from django.contrib import admin
from .models import LauncherToken, LauncherVersion


@admin.register(LauncherToken)
class LauncherTokenAdmin(admin.ModelAdmin):
    list_display = ["key_short", "user", "created_at"]
    search_fields = ["user__username", "key"]
    readonly_fields = ["key", "created_at"]

    def key_short(self, obj):
        return f"{obj.key[:16]}..."

    key_short.short_description = "Token"


@admin.register(LauncherVersion)
class LauncherVersionAdmin(admin.ModelAdmin):
    list_display = [
        "version",
        "platform",
        "is_active",
        "force_update",
        "file_size_display",
        "created_at",
    ]
    list_filter = ["platform", "is_active", "force_update"]
    search_fields = ["version", "release_notes"]
    readonly_fields = ["file_size", "created_at"]

    def file_size_display(self, obj):
        if obj.file_size:
            mb = obj.file_size / (1024 * 1024)
            return f"{mb:.1f} MB"
        return "—"

    file_size_display.short_description = "Hajmi"
