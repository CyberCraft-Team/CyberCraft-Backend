from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = [
        "created_at",
        "user",
        "title",
        "message",
        "notification_type",
        "is_read",
    ]
    list_filter = ["created_at", "notification_type", "is_read"]
    search_fields = ["user__username", "    title", "message"]
    readonly_fields = [
        "user",
        "title",
        "message",
        "notification_type",
        "is_read",
        "created_at",
    ]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
