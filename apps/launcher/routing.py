from django.urls import re_path
from .consumers import LauncherStatusConsumer, LauncherConsoleConsumer, LauncherEventsConsumer

websocket_urlpatterns = [
    re_path(r"ws/launcher/status/$", LauncherStatusConsumer.as_asgi()),
    re_path(r"ws/launcher/console/(?P<server_id>[0-9a-f-]+)/$", LauncherConsoleConsumer.as_asgi()),
    re_path(r"ws/launcher/events/$", LauncherEventsConsumer.as_asgi()),
]