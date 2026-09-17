import contextvars
import time

from common.logging_utils import bind_context, get_logger, log_event, reset_context
from common.logging_utils import request_id as correlation_id
from common.metrics import API_DURATION, API_REQUESTS

request_id_context = contextvars.ContextVar("request_id", default="")
logger = get_logger(__name__)


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request._mlops_request_logging = True
        request.request_id = correlation_id(request.headers.get("X-Request-ID"))
        token = request_id_context.set(request.request_id)
        logging_token = bind_context(request_id=request.request_id)
        started_at = time.monotonic()
        status_code = 500
        try:
            response = self.get_response(request)
            status_code = response.status_code
            response["X-Request-ID"] = request.request_id
            route = getattr(getattr(request, "resolver_match", None), "route", None) or "unmatched"
            API_DURATION.labels(method=request.method, route=route).observe(time.monotonic() - started_at)
            API_REQUESTS.labels(method=request.method, route=route, status=response.status_code).inc()
            return response
        except Exception as exception:
            self.process_exception(request, exception)
            raise
        finally:
            duration_ms = (time.monotonic() - started_at) * 1000
            route = getattr(getattr(request, "resolver_match", None), "route", None) or "unmatched"
            user = getattr(request, "user", None)
            tenant_id = getattr(user, "tenant_id", None) if getattr(user, "is_authenticated", False) else None
            try:
                probe = request.path.rstrip("/").split("/")[-1] in {
                    "live",
                    "livez",
                    "ready",
                    "readyz",
                    "health",
                    "healthz",
                    "metrics",
                }
                fields = {
                    "method": request.method,
                    "route": route,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "tenant_id": str(tenant_id) if tenant_id else None,
                }
                if status_code >= 400:
                    exc_info = getattr(request, "_mlops_exception", None)
                    log_event(
                        logger,
                        "ERROR" if status_code >= 500 else "WARNING",
                        "http.request.failed",
                        "HTTP request failed",
                        error_type=exc_info[0].__name__ if exc_info else None,
                        exc_info=exc_info,
                        **fields,
                    )
                elif not probe:
                    log_event(logger, "INFO", "http.request.finished", "HTTP request finished", **fields)
            finally:
                request.__dict__.pop("_mlops_exception", None)
                reset_context(logging_token)
                request_id_context.reset(token)

    def process_exception(self, request, exception):
        request._mlops_exception = (type(exception), exception, exception.__traceback__)
