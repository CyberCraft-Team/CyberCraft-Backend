from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import AdminToken


class AdminTokenAuthentication(TokenAuthentication):
    model = AdminToken
    keyword = "Token"

    def authenticate_credentials(self, key):
        try:
            token = AdminToken.objects.select_related("user").get(key=key)
        except AdminToken.DoesNotExist:
            raise AuthenticationFailed("Noto'g'ri token.")

        if token.is_expired():
            token.delete()
            raise AuthenticationFailed("Token muddati tugagan. Qaytadan kiring.")

        if not token.user.is_active:
            raise AuthenticationFailed("Foydalanuvchi faol emas.")

        if not token.user.is_staff:
            raise AuthenticationFailed("Admin huquqi yo'q.")

        return (token.user, token)
