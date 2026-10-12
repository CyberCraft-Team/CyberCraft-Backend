"""
Unit tests for core backend functionality.
Run: python manage.py test apps.accounts.tests
"""

from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from apps.accounts.models import (
    User,
    AuthToken,
    EmailVerificationToken,
    PasswordResetToken,
)
from apps.notifications.models import Notification
from apps.rewards.models import DailyBonus, CCTransaction


class UserModelTest(TestCase):
    """User model testlari."""

    def test_create_user(self):
        user = User.objects.create_user(
            username="testuser", email="test@test.com", password="testpass123"
        )
        self.assertEqual(user.username, "testuser")
        self.assertIsNotNone(user.minecraft_uuid)
        self.assertIsNotNone(user.referral_code)
        self.assertEqual(len(user.referral_code), 8)

    def test_unique_referral_code(self):
        user1 = User.objects.create_user(username="user1", password="pass1")
        user2 = User.objects.create_user(username="user2", password="pass2")
        self.assertNotEqual(user1.referral_code, user2.referral_code)

    def test_ban_fields(self):
        user = User.objects.create_user(username="banned_user", password="pass")
        user.is_banned = True
        user.ban_reason = "Test ban"
        user.banned_until = timezone.now() + timedelta(days=1)
        user.save()

        user.refresh_from_db()
        self.assertTrue(user.is_banned)
        self.assertEqual(user.ban_reason, "Test ban")


class TokenExpiryTest(TestCase):
    """Token expiry testlari."""

    def setUp(self):
        self.user = User.objects.create_user(username="tokenuser", password="pass123")

    def test_admin_token_expiry(self):
        token = AuthToken.issue(self.user, AuthToken.Scope.ADMIN)
        self.assertFalse(token.is_expired())

        token.expires_at = timezone.now() - timedelta(hours=1)
        token.save()
        self.assertTrue(token.is_expired())

    def test_launcher_token_expiry(self):
        token = AuthToken.issue(self.user, AuthToken.Scope.LAUNCHER)
        self.assertFalse(token.is_expired())

        token.expires_at = timezone.now() - timedelta(days=1)
        token.save()
        self.assertTrue(token.is_expired())

    def test_scope_lifetimes_differ(self):
        launcher = AuthToken.issue(self.user, AuthToken.Scope.LAUNCHER)
        admin = AuthToken.issue(self.user, AuthToken.Scope.ADMIN)
        ws = AuthToken.issue(self.user, AuthToken.Scope.WEBSOCKET)

        self.assertGreater(launcher.expires_at, admin.expires_at)
        self.assertGreater(admin.expires_at, ws.expires_at)

    def test_issuing_admin_token_revokes_the_previous_one(self):
        first = AuthToken.issue(self.user, AuthToken.Scope.ADMIN)
        second = AuthToken.issue(self.user, AuthToken.Scope.ADMIN)

        self.assertFalse(AuthToken.objects.filter(key=first.key).exists())
        self.assertTrue(AuthToken.objects.filter(key=second.key).exists())

    def test_launcher_tokens_accumulate(self):
        """Several devices may hold a launcher session at once."""
        AuthToken.issue(self.user, AuthToken.Scope.LAUNCHER)
        AuthToken.issue(self.user, AuthToken.Scope.LAUNCHER)

        self.assertEqual(
            AuthToken.objects.filter(
                user=self.user, scope=AuthToken.Scope.LAUNCHER
            ).count(),
            2,
        )

    def test_email_verification_token(self):
        token = EmailVerificationToken.objects.create(user=self.user)
        self.assertIsNotNone(token.token)
        self.assertFalse(token.is_expired())

    def test_password_reset_token(self):
        token = PasswordResetToken.objects.create(user=self.user)
        self.assertIsNotNone(token.token)
        self.assertFalse(token.is_expired())

        token.expires_at = timezone.now() - timedelta(hours=2)
        token.save()
        self.assertTrue(token.is_expired())

    def test_launcher_token_is_rejected_for_admin_scope(self):
        """Regression guard for the fallback removed in P2.

        AdminTokenAuthentication used to fall back to LauncherToken and
        accept it whenever the user was staff, so a 30-day player token
        doubled as an admin credential and the 24-hour admin session
        boundary meant nothing. A staff user must still be rejected here.
        """
        from rest_framework.test import APIRequestFactory

        from apps.accounts.authentication import AdminTokenAuthentication

        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()

        launcher_token = AuthToken.issue(self.user, AuthToken.Scope.LAUNCHER)

        request = APIRequestFactory().get(
            "/", HTTP_AUTHORIZATION=f"Token {launcher_token.key}"
        )
        with self.assertRaises(AuthenticationFailed):
            AdminTokenAuthentication().authenticate(request)

    def test_admin_token_is_rejected_for_launcher_scope(self):
        """The boundary holds in both directions."""
        from rest_framework.test import APIRequestFactory

        from apps.launcher.authentication import LauncherTokenAuthentication

        self.user.is_staff = True
        self.user.save()
        admin_token = AuthToken.issue(self.user, AuthToken.Scope.ADMIN)

        request = APIRequestFactory().get(
            "/", HTTP_AUTHORIZATION=f"Launcher {admin_token.key}"
        )
        with self.assertRaises(AuthenticationFailed):
            LauncherTokenAuthentication().authenticate(request)

    def test_admin_scope_requires_staff(self):
        from rest_framework.test import APIRequestFactory

        from apps.accounts.authentication import AdminTokenAuthentication

        token = AuthToken.issue(self.user, AuthToken.Scope.ADMIN)
        request = APIRequestFactory().get(
            "/", HTTP_AUTHORIZATION=f"Token {token.key}"
        )
        with self.assertRaises(AuthenticationFailed):
            AdminTokenAuthentication().authenticate(request)


class AuthAPITest(TestCase):
    """Auth API endpoint testlari."""

    def setUp(self):
        self.client = APIClient()
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        media_settings = override_settings(MEDIA_ROOT=Path(media.name))
        media_settings.enable()
        self.addCleanup(media_settings.disable)

    def test_register(self):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile

        # Generates a dummy 64x32 PNG skin
        file_io = io.BytesIO()
        image = Image.new("RGBA", size=(64, 32), color=(255, 0, 0, 255))
        image.save(file_io, "PNG")
        file_io.seek(0)

        dummy_skin = SimpleUploadedFile(
            name="steve.png",
            content=file_io.read(),
            content_type="image/png"
        )

        response = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "newuser",
                "email": "new@test.com",
                "password": "pass123456",
                "password_confirm": "pass123456",
                "skin": dummy_skin,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_login(self):
        User.objects.create_user(username="loginuser", password="pass123")
        response = self.client.post(
            "/api/v1/auth/launcher/login/",
            {"username": "loginuser", "password": "pass123"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.data)

    def test_invalid_login(self):
        response = self.client.post(
            "/api/v1/auth/launcher/login/",
            {"username": "nouser", "password": "wrong"},
            format="json",
        )
        self.assertIn(response.status_code, [400, 401])

    def test_password_reset_request(self):
        User.objects.create_user(
            username="resetuser", email="reset@test.com", password="pass123"
        )
        response = self.client.post(
            "/api/v1/auth/password-reset/",
            {"email": "reset@test.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

    def test_password_reset_nonexistent_email(self):
        """Xavfsizlik: mavjud bo'lmagan email ham 200 qaytarishi kerak."""
        response = self.client.post(
            "/api/v1/auth/password-reset/",
            {"email": "nonexistent@test.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)


class ReferralBonusTest(TestCase):
    """The bonus used to be awarded twice: once in UserRegisterSerializer
    and once again by the on_referral_bonus post_save receiver, which the
    serializer's own user.save() had already fired."""

    def setUp(self):
        self.inviter = User.objects.create_user(
            username="inviter", password="pass12345"
        )

    def test_bonus_is_awarded_exactly_once(self):
        invitee = User.objects.create_user(
            username="invitee", password="pass12345", referred_by=self.inviter
        )

        self.inviter.refresh_from_db()
        invitee.refresh_from_db()

        self.assertEqual(self.inviter.cc_balance, 10)
        self.assertEqual(invitee.cc_balance, 5)

    def test_one_transaction_row_per_side(self):
        invitee = User.objects.create_user(
            username="invitee2", password="pass12345", referred_by=self.inviter
        )

        self.assertEqual(
            CCTransaction.objects.filter(
                user=self.inviter, transaction_type="referral_inviter"
            ).count(),
            1,
        )
        self.assertEqual(
            CCTransaction.objects.filter(
                user=invitee, transaction_type="referral_invitee"
            ).count(),
            1,
        )

    def test_no_bonus_without_a_referrer(self):
        user = User.objects.create_user(username="solo", password="pass12345")
        self.assertEqual(user.cc_balance, 0)
        self.assertEqual(CCTransaction.objects.filter(user=user).count(), 0)


@override_settings(MOD_API_KEY="test-mod-key", DEBUG=False)
class ModApiKeyTest(TestCase):
    """/minecraft/verify/ decides who may join a game server. Before P2 it
    accepted any caller that could reach the backend."""

    ENDPOINTS = [
        ("post", "/api/v1/minecraft/verify/"),
        ("get", "/api/v1/rewards/player-rank/?username=someone"),
    ]

    def setUp(self):
        self.client = APIClient()

    def test_rejected_without_the_header(self):
        for method, url in self.ENDPOINTS:
            with self.subTest(url=url):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 403)

    def test_rejected_with_a_wrong_key(self):
        for method, url in self.ENDPOINTS:
            with self.subTest(url=url):
                response = getattr(self.client, method)(
                    url, HTTP_X_CYBERCRAFT_KEY="wrong-key"
                )
                self.assertEqual(response.status_code, 403)

    def test_accepted_with_the_right_key(self):
        """A correct key gets past the permission layer. The view may still
        answer 403 on its own merits -- an unknown player has no session --
        so this asserts the request was let through, not that it succeeded."""
        response = self.client.get(
            "/api/v1/rewards/player-rank/?username=nobody",
            HTTP_X_CYBERCRAFT_KEY="test-mod-key",
        )
        self.assertIn(response.status_code, (200, 404))

    @override_settings(MOD_API_KEY="", DEBUG=True)
    def test_open_in_development_when_no_key_is_configured(self):
        """A fresh checkout must still run. prod.py refuses to start with an
        empty MOD_API_KEY, so this cannot reach production."""
        response = self.client.get("/api/v1/rewards/player-rank/?username=nobody")
        self.assertNotEqual(response.status_code, 403)

    @override_settings(MOD_API_KEY="", DEBUG=False)
    def test_closed_when_no_key_and_not_debug(self):
        response = self.client.get("/api/v1/rewards/player-rank/?username=nobody")
        self.assertEqual(response.status_code, 403)


class HealthCheckTest(TestCase):
    """Health check endpoint testi."""

    def test_health_check(self):
        client = APIClient()
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=Path(media)):
            response = client.get("/api/v1/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "ok")
        self.assertIn("database", response.data["checks"])


class NotificationTest(TestCase):
    """Notification testlari."""

    def setUp(self):
        self.user = User.objects.create_user(username="notifuser", password="pass123")

    def test_create_notification(self):
        notif = Notification.send(
            user=self.user,
            title="Test",
            message="Test message",
            notification_type="info",
        )
        self.assertFalse(notif.is_read)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 2)

    def test_mark_read(self):
        notif = Notification.send(user=self.user, title="Read me", message="msg")
        notif.is_read = True
        notif.save()
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)


class DailyBonusTest(TestCase):
    """DailyBonus testlari."""

    def setUp(self):
        self.user = User.objects.create_user(username="bonususer", password="pass123")

    def test_claim_bonus(self):
        bonus = DailyBonus.objects.create(user=self.user)
        streak, amount = bonus.claim()
        self.assertEqual(streak, 1)
        self.assertFalse(bonus.can_claim_today())

    def test_streak_reset(self):
        bonus = DailyBonus.objects.create(user=self.user)
        bonus.last_claim = timezone.now().date() - timedelta(days=3)
        bonus.streak = 5
        bonus.save()

        streak, _ = bonus.claim()
        self.assertEqual(streak, 1)


class CredentialSecurityTest(TransactionTestCase):
    # Channels closes old connections around async DB calls. TransactionTestCase
    # avoids enclosing PostgreSQL connections in TestCase's atomic transaction.
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = User.objects.create_user(username="security-user", password="old-password")
        self.client = APIClient()

    def test_banned_launcher_token_is_rejected_after_issue(self):
        token = AuthToken.issue(self.user, AuthToken.Scope.LAUNCHER)
        self.user.is_banned = True
        self.user.save(update_fields=["is_banned"])
        self.client.credentials(HTTP_AUTHORIZATION=f"Launcher {token.key}")
        self.assertEqual(self.client.get("/api/v1/auth/launcher/me/").status_code, 401)

    def test_expired_ban_allows_authentication(self):
        self.user.is_banned = True
        self.user.banned_until = timezone.now() - timedelta(minutes=1)
        self.user.save()
        token = AuthToken.issue(self.user, AuthToken.Scope.LAUNCHER)
        self.client.credentials(HTTP_AUTHORIZATION=f"Launcher {token.key}")
        self.assertEqual(self.client.get("/api/v1/auth/launcher/me/").status_code, 200)

    def test_websocket_credentials_reject_inactive_and_banned_users(self):
        from asgiref.sync import async_to_sync
        from config.asgi import TokenAuthMiddleware
        from apps.launcher.consumers import WSTokenAuthMixin
        launcher = AuthToken.issue(self.user, AuthToken.Scope.LAUNCHER)
        websocket = AuthToken.issue(self.user, AuthToken.Scope.WEBSOCKET)
        middleware = TokenAuthMiddleware(None)
        for fields in ({"is_active": False}, {"is_active": True, "is_banned": True}):
            User.objects.filter(pk=self.user.pk).update(**fields)
            with self.subTest(fields=fields):
                self.assertTrue(async_to_sync(middleware.get_user_from_token)(launcher.key).is_anonymous)
                self.assertTrue(async_to_sync(WSTokenAuthMixin().get_user_from_ws_token)(websocket.key).is_anonymous)

    def test_password_reset_revokes_all_credentials_and_reset_links(self):
        from apps.yggdrasil_auth.models import YggdrasilSession, YggdrasilToken
        for scope in AuthToken.Scope:
            AuthToken.issue(self.user, scope)
        game_token = YggdrasilToken.objects.create(user=self.user)
        YggdrasilSession.objects.create(user=self.user, access_token=game_token.access_token, server_id="server")
        reset = PasswordResetToken.objects.create(user=self.user)
        other_reset = PasswordResetToken.objects.create(user=self.user)
        response = self.client.post("/api/v1/auth/password-reset/confirm/", {"token": reset.token, "new_password": "new-safe-password"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new-safe-password"))
        self.assertFalse(self.user.auth_tokens.exists())
        self.assertFalse(self.user.yggdrasil_tokens.exists())
        self.assertFalse(self.user.yggdrasil_sessions.exists())
        other_reset.refresh_from_db()
        self.assertTrue(other_reset.is_used)


class ReadinessSecurityTest(TestCase):
    def test_missing_media_directory_is_unready_without_disclosing_path(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=Path(directory) / "missing"):
            response = APIClient().get("/api/v1/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["status"], "error")
        self.assertNotIn("path", response.data["checks"]["media_storage"])

    def test_database_failure_is_unready_without_disclosing_error(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=Path(directory)):
            with patch("config.views.connection.cursor", side_effect=RuntimeError("private connection details")):
                response = APIClient().get("/api/v1/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["checks"]["database"], {"status": "error"})


    def test_redis_failure_is_unready(self):
        caches = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": "redis://127.0.0.1:6379/15"}}
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=Path(directory), CACHES=caches):
            with patch("config.views.cache.get", side_effect=ConnectionError("private Redis details")):
                response = APIClient().get("/api/v1/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["checks"]["cache"], {"status": "error"})


class ProductionMediaPermissionsTest(TestCase):
    def test_public_uploads_remain_readable_under_private_service_umask(self):
        import os
        import subprocess
        import sys
        script = """
import os, stat, sys, tempfile
from pathlib import Path
sys.argv = ["manage.py", "check"]
from django.conf import settings
settings.LOGGING = {"version": 1, "disable_existing_loggers": False}
import django
django.setup()
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
with tempfile.TemporaryDirectory() as directory:
    previous = os.umask(0o027)
    try:
        storage = FileSystemStorage(location=directory)
        name = storage.save("skins/player.png", ContentFile(b"public-media"))
    finally:
        os.umask(previous)
    assert stat.S_IMODE((Path(directory) / "skins").stat().st_mode) == 0o755
    assert stat.S_IMODE((Path(directory) / name).stat().st_mode) == 0o644
"""
        environment = {
            **os.environ,
            "PRODUCTION": "1",
            "SECRET_KEY": "media-test-secret-key-abcdefghijklmnopqrstuvwxyz-0123456789",
            "MOD_API_KEY": "media-test-mod-key",
            "ALLOWED_HOSTS": "localhost,127.0.0.1",
            "DATABASE_URL": "sqlite://:memory:",
            "USE_SQLITE": "0",
            "REDIS_URL": "redis://127.0.0.1:6379/15",
            "DJANGO_SETTINGS_MODULE": "config.settings",
        }
        result = subprocess.run([sys.executable, "-c", script], env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
