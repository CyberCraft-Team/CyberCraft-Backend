from django.db import models
from django.conf import settings


class Notification(models.Model):
    """Foydalanuvchi bildirishnomalari."""

    TYPE_CHOICES = [
        ("info", "Ma'lumot"),
        ("success", "Muvaffaqiyat"),
        ("warning", "Ogohlantirish"),
        ("reward", "Mukofot"),
        ("system", "Tizim"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, default="info"
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"

    def __str__(self):
        status = "✓" if self.is_read else "●"
        return f"{status} {self.user.username}: {self.title}"

    @classmethod
    def send(cls, user, title, message, notification_type="info"):
        """Helper to create a notification."""
        return cls.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type=notification_type,
        )
