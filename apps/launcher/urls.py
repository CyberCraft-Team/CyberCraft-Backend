from django.urls import path
from .views import (
    LauncherServersView,
    LauncherServerManifestView,
    LauncherUpdateCheckView,
    LauncherWSTokenView,
    ModFileDownloadView,
    ModpackFileDownloadView,
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
    path(
        "launcher/download/mod/<int:mod_id>/",
        ModFileDownloadView.as_view(),
        name="launcher-download-mod",
    ),
    path(
        "launcher/download/modpack-file/<int:file_id>/",
        ModpackFileDownloadView.as_view(),
        name="launcher-download-modpack-file",
    ),
]
