import contextvars
import time
import uuid

from common.metrics import API_DURATION, API_REQUESTS

request_id_context = contextvars.ContextVar("request_id", default="")


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_context.set(request.request_id)
        try:
            started_at = time.monotonic()
            response = self.get_response(request)
            response["X-Request-ID"] = request.request_id
            route = getattr(getattr(request, "resolver_match", None), "route", None) or "unmatched"
            API_DURATION.labels(method=request.method, route=route).observe(time.monotonic() - started_at)
            API_REQUESTS.labels(method=request.method, route=route, status=response.status_code).inc()
            return response
        finally:
            request_id_context.reset(token)
