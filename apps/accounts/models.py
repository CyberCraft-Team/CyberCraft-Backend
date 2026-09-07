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


class AuthTokenQuerySet(models.QuerySet):
    def valid(self):
        return self.filter(expires_at__gt=timezone.now())

    def expired(self):
        return self.filter(expires_at__lte=timezone.now())


class AuthToken(models.Model):
    """Opaque bearer token, scoped to what it is allowed to do.

    Replaces three near-identical models (AdminToken, LauncherToken,
    WSToken) that differed only in lifetime and key length. Keeping them
    separate is what allowed AdminTokenAuthentication to fall back to a
    30-day launcher token as an admin credential.

    Opaque and database-backed rather than a JWT on purpose: a ban has to
    take effect immediately, and revoking a row does that. A self-contained
    token would stay valid until it expired.
    """

    class Scope(models.TextChoices):
        LAUNCHER = "launcher", "Launcher"
        ADMIN = "admin", "Admin"
        WEBSOCKET = "ws", "WebSocket"

    LIFETIMES = {
        Scope.LAUNCHER: timedelta(days=30),
        Scope.ADMIN: timedelta(hours=24),
        Scope.WEBSOCKET: timedelta(minutes=10),
    }

    key = models.CharField(max_length=64, primary_key=True)
    user = models.ForeignKey(
        User, related_name="auth_tokens", on_delete=models.CASCADE
    )
    scope = models.CharField(
        max_length=16, choices=Scope.choices, default=Scope.LAUNCHER, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)

    objects = AuthTokenQuerySet.as_manager()

    class Meta:
        db_table = "auth_tokens"
        verbose_name = "Auth Token"
        verbose_name_plural = "Auth Tokens"
        indexes = [models.Index(fields=["user", "scope"])]

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        if not self.expires_at:
            self.expires_at = timezone.now() + self.LIFETIMES[self.Scope(self.scope)]
        return super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() > self.expires_at

    def touch(self):
        """Record use without a full save; best-effort, never fatal."""
        self.last_used_at = timezone.now()
        AuthToken.objects.filter(pk=self.pk).update(last_used_at=self.last_used_at)

    @classmethod
    def generate_key(cls):
        return binascii.hexlify(os.urandom(32)).decode()

    @classmethod
    def issue(cls, user, scope):
        """Mint a token. Admin scope is single-use-at-a-time, as before."""
        scope = cls.Scope(scope)
        if scope == cls.Scope.ADMIN:
            cls.objects.filter(user=user, scope=scope).delete()
        return cls.objects.create(user=user, scope=scope)

    @classmethod
    def purge_expired(cls):
        return cls.objects.expired().delete()[0]

    def __str__(self):
        return f"AuthToken({self.user.username}, {self.scope})"


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

