import logging

from django.db import connections
from django.http import HttpResponse, JsonResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.selectors import project_for_user
from apps.observability.selectors import latest_production_data
from apps.observability.services.models import model_observability
from common.metrics import shared_celery_metrics
from common.redis_client import redis_client

from .serializers import ProductionDataQuerySerializer


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
        from apps.observability.services.executions import execution_metrics

        return HttpResponse(
            generate_latest() + shared_celery_metrics() + execution_metrics(), content_type=CONTENT_TYPE_LATEST
        )


class ModelObservabilityEndpoint(APIView):
    def get(self, request, project_id):
        project = project_for_user(request.user, project_id)
        return Response(model_observability(project))


class RuntimeMetricsEndpoint(APIView):
    def get(self, request, project_id):
        from apps.observability.services.runtime_metrics import runtime_metrics

        return Response(
            runtime_metrics(project_for_user(request.user, project_id), window=request.query_params.get("window", "1h"))
        )


class ProductionDataEndpoint(APIView):
    def get(self, request, project_id):
        project = project_for_user(request.user, project_id)
        serializer = ProductionDataQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("count"):
            from apps.production.models import PredictionRecord

            qs = PredictionRecord.objects.filter(project=project)
            if serializer.validated_data.get("version_id"):
                qs = qs.filter(model_version__public_id=serializer.validated_data["version_id"])
            return Response({"count": qs.count()})
        kwargs = {
            "limit": serializer.validated_data.get("limit"),
            "version_id": serializer.validated_data.get("version_id"),
        }
        offset = serializer.validated_data.get("offset", 0)
        if offset:
            kwargs["offset"] = offset
        return Response(latest_production_data(project, **kwargs))
