from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .views import HealthCheckView

api_v1_patterns = [
    path("", include("apps.accounts.urls")),
    path("", include("apps.launcher.urls")),
    path("", include("apps.servers.urls")),
    path("", include("apps.news.urls")),
    path("", include("apps.voting.urls")),
    path("rewards/", include("apps.rewards.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1_patterns)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
