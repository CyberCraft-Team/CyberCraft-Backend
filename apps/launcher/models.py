from django.db import models
from django.conf import settings
import secrets
from datetime import timedelta
from django.utils import timezone


class LauncherToken(models.Model):
    TOKEN_LIFETIME_DAYS = 30

    key = models.CharField(max_length=64, primary_key=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="launcher_token",
        on_delete=models.CASCADE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "launcher_tokens"
        verbose_name = "Launcher Token"
        verbose_name_plural = "Launcher Tokens"

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=self.TOKEN_LIFETIME_DAYS)
        return super().save(*args, **kwargs)

    def is_expired(self):
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at

    @classmethod
    def generate_key(cls):
        return secrets.token_hex(32)

    def __str__(self):
        return f"{self.user.username} - {self.key[:8]}..."


class LauncherVersion(models.Model):
    PLATFORM_CHOICES = [
        ("win32", "Windows"),
        ("darwin", "macOS"),
        ("linux", "Linux"),
    ]

    version = models.CharField(max_length=20, help_text="Versiya raqami, masalan: 2.2.0")
    platform = models.CharField(
        max_length=10, choices=PLATFORM_CHOICES, default="win32"
    )
    download_file = models.FileField(
        upload_to="launcher/releases/",
        help_text="Installer fayli (.exe, .dmg, .tar.gz)",
    )
    file_size = models.BigIntegerField(default=0, help_text="Fayl hajmi (baytlarda)")
    release_notes = models.TextField(blank=True, default="", help_text="O'zgarishlar ro'yxati")
    is_active = models.BooleanField(default=True, help_text="Aktiv versiya sifatida belgilash")
    force_update = models.BooleanField(
        default=True,
        help_text="Majburiy yangilanish (foydalanuvchi o'tkazib yubora olmaydi)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "launcher_versions"
        verbose_name = "Launcher Version"
        verbose_name_plural = "Launcher Versions"
        ordering = ["-created_at"]
        unique_together = ["version", "platform"]

    def save(self, *args, **kwargs):
        if self.download_file and not self.file_size:
            self.file_size = self.download_file.size
        super().save(*args, **kwargs)

    def __str__(self):
        return f"v{self.version} ({self.get_platform_display()})"
