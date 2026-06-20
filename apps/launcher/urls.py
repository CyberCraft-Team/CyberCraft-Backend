from django.urls import path
from .views import (
    LauncherServersView,
    LauncherServerManifestView,
    LauncherUpdateCheckView,
    LauncherWSTokenView,
)

urlpatterns = [
    path("launcher/servers/", LauncherServersView.as_view(), name="launcher-servers"),
    path(
        "launcher/servers/<str:server_id>/manifest/",
        LauncherServerManifestView.as_view(),
        name="launcher-server-manifest",
    ),
    path(
        "launcher/update/",
        LauncherUpdateCheckView.as_view(),
        name="launcher-update-check",
    ),
    path(
        "launcher/ws-token/",
        LauncherWSTokenView.as_view(),
        name="launcher-ws-token",
    ),
]
