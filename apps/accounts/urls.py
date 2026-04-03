from django.urls import path
from .views import (
    LauncherLoginView,
    LauncherLogoutView,
    LauncherMeView,
    AdminLoginView,
    AdminLogoutView,
    AdminMeView,
    AdminUsersListView,
    AdminUserDetailView,
    UserRegisterView,
    SkinUploadView,
    CapeUploadView,
    minecraft_auth,
    MinecraftVerifyView,
    MinecraftSessionCreateView,
    SendVerificationEmailView,
    VerifyEmailView,
    RequestPasswordResetView,
    ConfirmPasswordResetView,
    GoogleLoginView,
    TelegramLoginView,
)

urlpatterns = [
    path("auth/register/", UserRegisterView.as_view(), name="user-register"),
    path("auth/launcher/login/", LauncherLoginView.as_view(), name="launcher-login"),
    path("auth/launcher/logout/", LauncherLogoutView.as_view(), name="launcher-logout"),
    path("auth/launcher/me/", LauncherMeView.as_view(), name="launcher-me"),
    path("auth/launcher/skin/", SkinUploadView.as_view(), name="launcher-skin-upload"),
    path("auth/launcher/cape/", CapeUploadView.as_view(), name="launcher-cape-upload"),
    path(
        "auth/verify-email/send/",
        SendVerificationEmailView.as_view(),
        name="send-verification",
    ),
    path("auth/verify-email/confirm/", VerifyEmailView.as_view(), name="verify-email"),
    path(
        "auth/password-reset/",
        RequestPasswordResetView.as_view(),
        name="request-password-reset",
    ),
    path(
        "auth/password-reset/confirm/",
        ConfirmPasswordResetView.as_view(),
        name="confirm-password-reset",
    ),
    path("auth/admin/login/", AdminLoginView.as_view(), name="admin-login"),
    path("auth/admin/logout/", AdminLogoutView.as_view(), name="admin-logout"),
    path("auth/admin/me/", AdminMeView.as_view(), name="admin-me"),
    path("admin/users/", AdminUsersListView.as_view(), name="admin-users-list"),
    path(
        "admin/users/<int:pk>/", AdminUserDetailView.as_view(), name="admin-user-detail"
    ),
    path("minecraft/auth/", minecraft_auth, name="minecraft-auth"),
    path("minecraft/verify/", MinecraftVerifyView.as_view(), name="minecraft-verify"),
    path(
        "minecraft/session/create/",
        MinecraftSessionCreateView.as_view(),
        name="minecraft-session-create",
    ),
    path("auth/google-login/", GoogleLoginView.as_view(), name="google-login"),
    path("auth/telegram-login/", TelegramLoginView.as_view(), name="telegram-login"),
]
