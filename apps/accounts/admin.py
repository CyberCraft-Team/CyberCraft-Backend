from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, AuthToken


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = [
        "username",
        "email",
        "cc_balance",
        "is_whitelisted",
        "rank",
        "is_operator",
        "is_staff",
    ]
    list_filter = ["is_whitelisted", "rank", "is_operator", "is_staff", "is_active"]
    search_fields = ["username", "email"]

    fieldsets = UserAdmin.fieldsets + (
        (
            "Minecraft Info",
            {
                "fields": (
                    "minecraft_uuid",
                    "cc_balance",
                    "is_whitelisted",
                    "rank",
                    "is_operator",
                )
            },
        ),
    )


@admin.register(AuthToken)
class AuthTokenAdmin(admin.ModelAdmin):
    list_display = ["key_short", "user", "scope", "created_at", "expires_at", "last_used_at"]
    list_filter = ["scope"]
    search_fields = ["user__username", "key"]
    readonly_fields = ["key", "created_at", "last_used_at"]

    @admin.display(description="Token")
    def key_short(self, obj):
        return f"{obj.key[:16]}…"
