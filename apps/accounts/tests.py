"""
Unit tests for core backend functionality.
Run: python manage.py test apps.accounts.tests
"""

from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta
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


class HealthCheckTest(TestCase):
    """Health check endpoint testi."""

    def test_health_check(self):
        client = APIClient()
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
