"""
Custom DRF exception handler — yagona error format.
Response format: {"error": "...", "code": "...", "details": {...}}
"""

import logging
from rest_framework.views import exception_handler
from rest_framework import status
from django.http import Http404
from django.core.exceptions import PermissionDenied

logger = logging.getLogger(__name__)

ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    429: "throttled",
    500: "server_error",
}


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        logger.exception("Unhandled exception: %s", exc)
        return None

    status_code = response.status_code
    error_code = ERROR_CODES.get(status_code, "error")

    if isinstance(response.data, dict):
        if "error" in response.data:
            error_msg = response.data["error"]
            details = {k: v for k, v in response.data.items() if k != "error"}
        elif "detail" in response.data:
            error_msg = str(response.data["detail"])
            details = {}
        else:
            error_msg = "Validatsiya xatosi"
            details = response.data
    elif isinstance(response.data, list):
        error_msg = response.data[0] if response.data else "Xatolik yuz berdi"
        details = {}
    else:
        error_msg = str(response.data)
        details = {}

    response.data = {
        "error": error_msg,
        "code": error_code,
    }
    if details:
        response.data["details"] = details

    return response
