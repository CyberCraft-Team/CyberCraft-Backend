from django.db import models
from django.conf import settings


class AuditLog(models.Model):
    """Admin harakatlari logi."""

    ACTION_CHOICES = [
        ("create", "Yaratildi"),
        ("update", "Yangilandi"),
        ("delete", "O'chirildi"),
        ("login", "Kirish"),
        ("logout", "Chiqish"),
        ("ban", "Bloklash"),
        ("unban", "Blokdan chiqarish"),
        ("rank_change", "Rank o'zgartirish"),
        ("cc_adjust", "CC o'zgartirish"),
        ("other", "Boshqa"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=100, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-created_at"]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"

    def __str__(self):
        username = self.user.username if self.user else "system"
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {username}: {self.get_action_display()}"

    @classmethod
    def log(
        cls,
        user,
        action,
        description="",
        model_name="",
        object_id="",
        changes=None,
        ip_address=None,
    ):
        """Helper method to create audit log entry."""
        return cls.objects.create(
            user=user,
            action=action,
            model_name=model_name,
            object_id=str(object_id) if object_id else "",
            changes=changes or {},
            ip_address=ip_address,
            description=description,
        )
