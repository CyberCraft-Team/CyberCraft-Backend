import binascii
import os
import secrets
import string
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from datetime import timedelta
import uuid


class User(AbstractUser):
    minecraft_uuid = models.CharField(max_length=36, blank=True, null=True, unique=True)
    skin = models.ImageField(upload_to="skins/", blank=True, null=True)
    skin_face = models.ImageField(upload_to="skin_faces/", blank=True, null=True)
    cape = models.ImageField(upload_to="capes/", blank=True, null=True)
    is_whitelisted = models.BooleanField(default=False)
    is_operator = models.BooleanField(default=False)

    is_email_verified = models.BooleanField(default=False)

    is_banned = models.BooleanField(default=False)
    ban_reason = models.CharField(max_length=255, blank=True, default="")
    banned_until = models.DateTimeField(null=True, blank=True)
    telegram_id = models.BigIntegerField(unique=True, null=True, blank=True)

    referral_code = models.CharField(max_length=8, unique=True, blank=True, null=True)
    referred_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="referrals",
    )
    cc_balance = models.IntegerField(default=0)
    rank = models.CharField(max_length=20, default="Player")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users"
        verbose_name = "User"
        verbose_name_plural = "Users"

    def save(self, *args, **kwargs):
        if not self.minecraft_uuid:
            offline_uuid = uuid.uuid3(
                uuid.NAMESPACE_DNS, f"OfflinePlayer:{self.username}"
            )
            self.minecraft_uuid = str(offline_uuid)

        if not self.referral_code:
            self.referral_code = self._generate_referral_code()

        super().save(*args, **kwargs)

    @staticmethod
    def _generate_referral_code():
        chars = string.ascii_uppercase + string.digits
        from apps.accounts.models import User

        while True:
            code = "".join(secrets.choice(chars) for _ in range(8))
            if not User.objects.filter(referral_code=code).exists():
                return code

    def __str__(self):
        return self.username


class AdminToken(models.Model):
    TOKEN_LIFETIME_HOURS = 24

    key = models.CharField(max_length=40, primary_key=True)
    user = models.OneToOneField(
        User, related_name="admin_token", on_delete=models.CASCADE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "admin_tokens"
        verbose_name = "Admin Token"
        verbose_name_plural = "Admin Tokens"

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(
                hours=self.TOKEN_LIFETIME_HOURS
            )
        return super().save(*args, **kwargs)

    def is_expired(self):
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at

    @classmethod
    def generate_key(cls):
        return binascii.hexlify(os.urandom(20)).decode()

    def __str__(self):
        return f"AdminToken({self.user.username})"


class EmailVerificationToken(models.Model):
    """Email tasdiqlash tokeni."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="email_tokens"
    )
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "email_verification_tokens"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(48)
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=24)
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"EmailToken({self.user.username})"


class PasswordResetToken(models.Model):
    """Parol tiklash tokeni."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="password_reset_tokens"
    )
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        db_table = "password_reset_tokens"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(48)
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=1)
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"ResetToken({self.user.username})"


class MinecraftSession(models.Model):
    """Vaqtinchalik Minecraft kirish sessiyasi.

    Launcher serverga ulanishdan oldin session yaratadi.
    Server mod player join bo'lganda session borligini tekshiradi.
    Session 60 soniyadan keyin o'z-o'zidan eskiradi.
    """

    SESSION_LIFETIME_SECONDS = 60

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="minecraft_sessions"
    )
    username = models.CharField(max_length=150)
    uuid = models.CharField(max_length=36)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "minecraft_sessions"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(
                seconds=self.SESSION_LIFETIME_SECONDS
            )
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() > self.expires_at

    @classmethod
    def cleanup_expired(cls):
        """Eskirgan sessionlarni tozalash."""
        cls.objects.filter(expires_at__lt=timezone.now()).delete()

    def __str__(self):
        return f"MinecraftSession({self.username}, expires={self.expires_at})"

