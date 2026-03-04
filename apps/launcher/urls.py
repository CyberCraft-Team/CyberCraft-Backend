from django.urls import path
from .views import (
    LauncherServersView,
    LauncherServerManifestView,
    LauncherUpdateCheckView,
)

urlpatterns = [
    path("launcher/servers/", LauncherServersView.as_view(), name="launcher-servers"),
    path(
        "servers/<str:server_id>/manifest/",
        LauncherServerManifestView.as_view(),
        name="launcher-server-manifest",
    ),
    path(
        "launcher/update/",
        LauncherUpdateCheckView.as_view(),
        name="launcher-update-check",
    ),
]
