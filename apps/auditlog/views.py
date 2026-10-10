from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import AdminTokenAuthentication
from .models import AuditLog


class RecentAuditLogView(APIView):
    """A bounded, read-only activity feed for the administrator overview."""

    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request):
        entries = AuditLog.objects.select_related("user").order_by(
            "-created_at", "-pk"
        )[:10]
        return Response([
            {
                "id": entry.pk,
                "username": entry.user.username if entry.user else None,
                "action": entry.action,
                "description": entry.description,
                "created_at": entry.created_at.isoformat(),
            }
            for entry in entries
        ])
