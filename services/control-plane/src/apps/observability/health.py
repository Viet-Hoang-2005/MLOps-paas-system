import logging
import os

from django.db import connections
from django.http import HttpResponse, JsonResponse
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, CollectorRegistry, generate_latest, multiprocess
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from common.telemetry.metrics import shared_celery_metrics
from infrastructure.redis import redis_client

logger = logging.getLogger(__name__)


class LiveEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):
        return JsonResponse({"status": "ok"})


class ReadyEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):
        checks = {}
        try:
            connections["default"].cursor().execute("SELECT 1")
            checks["postgres"] = "ok"
        except Exception:
            logger.warning("Readiness check failed for postgres", exc_info=True)
            checks["postgres"] = "unavailable"
        try:
            checks["redis"] = "ok" if redis_client().ping() else "unavailable"
        except Exception:
            logger.warning("Readiness check failed for redis", exc_info=True)
            checks["redis"] = "unavailable"
        status_code = 200 if all(value == "ok" for value in checks.values()) else 503
        return JsonResponse(
            {"status": "ok" if status_code == 200 else "unavailable", "checks": checks}, status=status_code
        )


class MetricsEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):
        from apps.observability.execution.reconciliation import execution_metrics

        registry = REGISTRY
        if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(registry)
        return HttpResponse(
            generate_latest(registry) + shared_celery_metrics() + execution_metrics(),
            content_type=CONTENT_TYPE_LATEST,
        )
