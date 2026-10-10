from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import AuthToken, User
from .models import AuditLog


class RecentActivityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(username="activity-admin", is_staff=True)

    def test_only_admin_scope_can_read_activity(self):
        url = "/api/v1/admin/activity/"
        self.assertEqual(self.client.get(url).status_code, 401)
        launcher = AuthToken.issue(self.admin, AuthToken.Scope.LAUNCHER)
        self.client.credentials(HTTP_AUTHORIZATION=f"Launcher {launcher.key}")
        self.assertEqual(self.client.get(url).status_code, 401)
        member = User.objects.create_user(username="activity-member")
        token = AuthToken.issue(member, AuthToken.Scope.ADMIN)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.assertEqual(self.client.get(url).status_code, 401)

    def test_feed_is_bounded_newest_first_and_excludes_private_fields(self):
        for index in range(12):
            AuditLog.log(self.admin, "update", description=str(index),
                         changes={"private": "data"}, ip_address="127.0.0.1")
        newest = AuditLog.log(None, "other", description="system")
        token = AuthToken.issue(self.admin, AuthToken.Scope.ADMIN)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = self.client.get("/api/v1/admin/activity/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 10)
        self.assertEqual(response.data[0]["id"], newest.pk)
        self.assertIsNone(response.data[0]["username"])
        self.assertEqual(response.data[1]["description"], "11")
        self.assertNotIn("changes", response.data[1])
        self.assertNotIn("ip_address", response.data[1])
        self.assertEqual(self.client.post("/api/v1/admin/activity/", {}).status_code, 405)
