from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, AdminToken


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


@admin.register(AdminToken)
class AdminTokenAdmin(admin.ModelAdmin):
    list_display = ["key", "user", "created_at"]
    search_fields = ["user__username"]
    readonly_fields = ["key", "created_at"]
