"""
Unit tests for core backend functionality.
Run: python manage.py test apps.accounts.tests
"""

from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from apps.accounts.models import (
    User,
    AdminToken,
    EmailVerificationToken,
    PasswordResetToken,
)
from apps.launcher.models import LauncherToken
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
        token = AdminToken.objects.create(user=self.user)
        self.assertFalse(token.is_expired())

        token.expires_at = timezone.now() - timedelta(hours=1)
        token.save()
        self.assertTrue(token.is_expired())

    def test_launcher_token_expiry(self):
        token = LauncherToken.objects.create(user=self.user)
        self.assertFalse(token.is_expired())

        token.expires_at = timezone.now() - timedelta(days=1)
        token.save()
        self.assertTrue(token.is_expired())

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


class AuthAPITest(TestCase):
    """Auth API endpoint testlari."""

    def setUp(self):
        self.client = APIClient()

    def test_register(self):
        response = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "newuser",
                "email": "new@test.com",
                "password": "pass123456",
                "password_confirm": "pass123456",
            },
            format="json",
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
        response = client.get("/api/health/")
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
