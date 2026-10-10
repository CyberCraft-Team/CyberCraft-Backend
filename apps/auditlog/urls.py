from django.urls import path
from .views import RecentAuditLogView

urlpatterns = [
    path("admin/activity/", RecentAuditLogView.as_view(), name="admin-activity"),
]
