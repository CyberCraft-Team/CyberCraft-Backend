from django.db import models

# LauncherToken and WSToken moved to apps.accounts.models.AuthToken in P2,
# where they became scopes on a single model rather than three near-identical
# tables. Import AuthToken from there.


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
