from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import uuid


class YggdrasilToken(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="yggdrasil_tokens"
    )
    access_token = models.CharField(max_length=64, unique=True, db_index=True)
    client_token = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "yggdrasil_tokens"
        verbose_name = "Yggdrasil Token"
        verbose_name_plural = "Yggdrasil Tokens"

    def save(self, *args, **kwargs):
        if not self.access_token:
            self.access_token = uuid.uuid4().hex
        if not self.client_token:
            self.client_token = uuid.uuid4().hex
        if not self.expires_at:
            # Standard 30 days lifetime
            self.expires_at = timezone.now() + timedelta(days=30)
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"YggToken({self.user.username}, active={not self.is_expired()})"


class YggdrasilSession(models.Model):
    """Active game join session (binds user, access_token, and serverId)."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="yggdrasil_sessions"
    )
    access_token = models.CharField(max_length=64, db_index=True)
    server_id = models.CharField(max_length=128, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "yggdrasil_sessions"
        verbose_name = "Yggdrasil Session"
        verbose_name_plural = "Yggdrasil Sessions"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            # Standard 60 seconds lifetime
            self.expires_at = timezone.now() + timedelta(seconds=60)
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() > self.expires_at

    @classmethod
    def cleanup_expired(cls):
        cls.objects.filter(expires_at__lt=timezone.now()).delete()

    def __str__(self):
        return f"YggSession({self.user.username}, server={self.server_id[:16]}...)"
