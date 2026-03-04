from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import LauncherToken


class LauncherTokenAuthentication(BaseAuthentication):
    keyword = "Launcher"

    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")

        if not auth_header:
            return None

        parts = auth_header.split()

        if len(parts) != 2:
            return None

        keyword, token = parts

        if keyword not in ["Launcher", "Token"]:
            return None

        try:
            launcher_token = LauncherToken.objects.select_related("user").get(key=token)
        except LauncherToken.DoesNotExist:
            raise AuthenticationFailed("Token noto'g'ri yoki muddati tugagan")

        if launcher_token.is_expired():
            launcher_token.delete()
            raise AuthenticationFailed("Token muddati tugagan. Qaytadan kiring.")

        if not launcher_token.user.is_active:
            raise AuthenticationFailed("Foydalanuvchi faol emas")

        return (launcher_token.user, launcher_token)

    def authenticate_header(self, request):
        return self.keyword
