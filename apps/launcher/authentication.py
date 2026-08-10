from apps.accounts.authentication import ScopedTokenAuthentication
from apps.accounts.models import AuthToken


class LauncherTokenAuthentication(ScopedTokenAuthentication):
    """Player-facing credential, used by the launcher and the website.

    Accepts both `Launcher` and `Token` as the header keyword: the launcher
    sends the former and the website the latter, and changing either would
    be a client break for no gain.
    """

    scope = AuthToken.Scope.LAUNCHER
    keywords = ("Launcher", "Token")
