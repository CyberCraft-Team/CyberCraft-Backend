from django.urls import path
from .views import (
    YggdrasilMetadataView,
    YggdrasilAuthenticateView,
    YggdrasilLauncherAuthenticateView,
    YggdrasilRefreshView,
    YggdrasilValidateView,
    YggdrasilInvalidateView,
    YggdrasilSignoutView,
    YggdrasilJoinView,
    YggdrasilHasJoinedView,
    YggdrasilProfileView,
    YggdrasilProfileLookupView,
)

urlpatterns = [
    # Root metadata endpoint
    path("", YggdrasilMetadataView.as_view(), name="yggdrasil-metadata"),

    # Authserver endpoints
    path("authserver/authenticate", YggdrasilAuthenticateView.as_view(), name="yggdrasil-authenticate"),
    path("authserver/launcher-authenticate", YggdrasilLauncherAuthenticateView.as_view(), name="yggdrasil-launcher-authenticate"),
    path("authserver/refresh", YggdrasilRefreshView.as_view(), name="yggdrasil-refresh"),
    path("authserver/validate", YggdrasilValidateView.as_view(), name="yggdrasil-validate"),
    path("authserver/invalidate", YggdrasilInvalidateView.as_view(), name="yggdrasil-invalidate"),
    path("authserver/signout", YggdrasilSignoutView.as_view(), name="yggdrasil-signout"),

    # Sessionserver endpoints
    path("sessionserver/session/minecraft/join", YggdrasilJoinView.as_view(), name="yggdrasil-join"),
    path("sessionserver/session/minecraft/hasJoined", YggdrasilHasJoinedView.as_view(), name="yggdrasil-has-joined"),
    path("sessionserver/session/minecraft/profile/<str:uuid>", YggdrasilProfileView.as_view(), name="yggdrasil-profile"),

    # API endpoints
    path("api/profiles/minecraft", YggdrasilProfileLookupView.as_view(), name="yggdrasil-profile-lookup"),
]
