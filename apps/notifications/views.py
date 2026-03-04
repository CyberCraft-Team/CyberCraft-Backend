from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import ListAPIView
from apps.launcher.authentication import LauncherTokenAuthentication
from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(ListAPIView):
    """Foydalanuvchi bildirishnomalari ro'yxati."""

    authentication_classes = [LauncherTokenAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class NotificationUnreadCountView(APIView):
    """O'qilmagan bildirishnomalar soni."""

    authentication_classes = [LauncherTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({"unread_count": count})


class NotificationMarkReadView(APIView):
    """Bildirishnomani o'qilgan deb belgilash."""

    authentication_classes = [LauncherTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            notification = Notification.objects.get(pk=pk, user=request.user)
            notification.is_read = True
            notification.save(update_fields=["is_read"])
            return Response({"message": "O'qilgan deb belgilandi"})
        except Notification.DoesNotExist:
            return Response({"error": "Bildirishnoma topilmadi"}, status=404)


class NotificationMarkAllReadView(APIView):
    """Barcha bildirishnomalarni o'qilgan deb belgilash."""

    authentication_classes = [LauncherTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).update(
            is_read=True
        )
        return Response(
            {"message": f"{count} ta bildirishnoma o'qilgan deb belgilandi"}
        )
