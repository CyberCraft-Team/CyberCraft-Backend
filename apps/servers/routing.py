from django.urls import re_path
from .consumers import ServerConsoleConsumer

websocket_urlpatterns = [
    re_path(
        r"ws/server/(?P<server_id>[0-9a-f-]+)/console/$",
        ServerConsoleConsumer.as_asgi(),
    ),
]
