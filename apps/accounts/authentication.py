from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import AuthToken


class ScopedTokenAuthentication(BaseAuthentication):
    """Bearer authentication against a single AuthToken scope.

    Subclasses set `scope`. A token minted for one scope is never accepted
    for another: before P2, AdminTokenAuthentication fell back to accepting
    a 30-day launcher token as an admin credential, which collapsed the
    24-hour admin session boundary entirely.
    """

    scope = None
    keywords = ("Token",)

    def authenticate(self, request):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header:
            return None

        parts = header.split()
        if len(parts) != 2:
            return None

        keyword, key = parts
        if keyword not in self.keywords:
            return None

        try:
            token = AuthToken.objects.select_related("user").get(
                key=key, scope=self.scope
            )
        except AuthToken.DoesNotExist:
            raise AuthenticationFailed("Token noto'g'ri yoki muddati tugagan.")

        if token.is_expired():
            token.delete()
            raise AuthenticationFailed("Token muddati tugagan. Qaytadan kiring.")

        if not token.user.is_active:
            raise AuthenticationFailed("Foydalanuvchi faol emas.")

        self.check_user(token.user)
        token.touch()
        return (token.user, token)

    def check_user(self, user):
        """Extra per-scope requirements. Overridden by admin scope."""

    def authenticate_header(self, request):
        return self.keywords[0]


class AdminTokenAuthentication(ScopedTokenAuthentication):
    scope = AuthToken.Scope.ADMIN

    def check_user(self, user):
        if not (user.is_staff or user.is_superuser):
            raise AuthenticationFailed("Admin huquqi yo'q.")
