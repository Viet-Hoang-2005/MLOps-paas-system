from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_exception_handler


class Conflict(APIException):
    status_code = 409
    default_code = "conflict"
    default_detail = "The resource conflicts with the current state."


class ServiceUnavailable(APIException):
    status_code = 503
    default_code = "service_unavailable"
    default_detail = "A required service is unavailable."


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return response
    detail = response.data
    if isinstance(detail, dict) and set(detail) == {"detail"}:
        detail = detail["detail"]
    response.data = {
        "error": {
            "code": getattr(exc, "default_code", "request_failed"),
            "detail": detail,
        }
    }
    return response
