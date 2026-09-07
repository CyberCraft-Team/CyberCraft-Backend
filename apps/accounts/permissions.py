"""Permission classes shared across apps."""

import logging
import secrets

from django.conf import settings
from rest_framework.permissions import BasePermission

logger = logging.getLogger(__name__)

MOD_KEY_HEADER = "HTTP_X_CYBERCRAFT_KEY"


class IsTrustedMod(BasePermission):
    """Shared-secret gate for the in-game mod endpoints.

    /minecraft/verify/ and /rewards/player-rank(s)/ are called by
    cybercraftauth and cybercraftranks running on the game servers, not by
    a logged-in user, so there is no token to present. They were previously
    open to anyone who could reach the backend: /minecraft/verify/ answers
    whether a named player may join, and player-rank leaks the roster.

    Verification uses compare_digest so a wrong key cannot be recovered by
    timing the response.
    """

    message = "Invalid or missing mod API key."

    def has_permission(self, request, view):
        expected = getattr(settings, "MOD_API_KEY", "")

        if not expected:
            # prod.py refuses to start without MOD_API_KEY, so this branch is
            # development only. Warn rather than fail so a fresh checkout
            # still runs.
            if settings.DEBUG:
                logger.warning(
                    "MOD_API_KEY is not set; %s is unauthenticated. "
                    "Set it before exposing this backend.",
                    request.path,
                )
                return True
            return False

        provided = request.META.get(MOD_KEY_HEADER, "")
        if not provided:
            return False

        return secrets.compare_digest(provided, expected)
