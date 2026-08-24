from common.metrics import shared_celery_metrics
from django.conf import settings
from django.db import connections
from django.http import HttpResponse, JsonResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis import Redis
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.selectors import project_for_user
from apps.observability.selectors import latest_production_data
from apps.observability.services.models import model_observability

from .serializers import ProductionDataQuerySerializer


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
        except Exception as exc:
            checks["postgres"] = str(exc)
        try:
            checks["redis"] = "ok" if Redis.from_url(settings.REDIS_URL).ping() else "failed"
        except Exception as exc:
            checks["redis"] = str(exc)
        status_code = 200 if all(value == "ok" for value in checks.values()) else 503
        return JsonResponse(
            {"status": "ok" if status_code == 200 else "unavailable", "checks": checks}, status=status_code
        )


class MetricsEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):
        return HttpResponse(generate_latest() + shared_celery_metrics(), content_type=CONTENT_TYPE_LATEST)


class ModelObservabilityEndpoint(APIView):
    def get(self, request, project_id):
        project = project_for_user(request.user, project_id)
        return Response(model_observability(project))


class ProductionDataEndpoint(APIView):
    def get(self, request, project_id):
        project = project_for_user(request.user, project_id)
        serializer = ProductionDataQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return Response(
            latest_production_data(
                project,
                limit=serializer.validated_data.get("limit"),
            )
        )
