"""Helpers for recording administrative actions.

The AuditLog model, its admin and its migration have existed since the
project started, but AuditLog.log() was never called from anywhere, so
none of the ban, staff or superuser changes left a trace. These helpers
give the views a one-liner.
"""

import logging

from .models import AuditLog

logger = logging.getLogger(__name__)


def client_ip(request):
    """Best-effort client address, honouring the reverse proxy.

    nginx sets X-Forwarded-For; the left-most entry is the original client.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def record(request, action, *, target=None, description="", changes=None):
    """Write an audit entry for an action taken by request.user.

    Never raises: an audit failure must not turn a successful ban into a
    500. Failures are logged instead.
    """
    try:
        return AuditLog.log(
            user=request.user if request.user.is_authenticated else None,
            action=action,
            description=description,
            model_name=target.__class__.__name__ if target is not None else "",
            object_id=getattr(target, "pk", "") or "",
            changes=changes or {},
            ip_address=client_ip(request),
        )
    except Exception:
        logger.exception("Failed to write audit log for action %s", action)
        return None


def record_flag_change(request, target_user, field, value):
    """Audit a boolean flag flip on a user account."""
    return record(
        request,
        "update",
        target=target_user,
        description=f"{target_user.username}: {field} -> {value}",
        changes={field: value},
    )
