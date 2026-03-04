from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "user", "action", "model_name", "description"]
    list_filter = ["action", "created_at"]
    search_fields = ["user__username", "description", "model_name"]
    readonly_fields = [
        "user",
        "action",
        "model_name",
        "object_id",
        "changes",
        "ip_address",
        "description",
        "created_at",
    ]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
