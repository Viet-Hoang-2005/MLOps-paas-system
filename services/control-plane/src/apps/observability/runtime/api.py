from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.projects.selectors import project_for_user
from apps.observability.selectors import latest_production_data
from apps.observability.serializers import ProductionDataQuerySerializer

class RuntimeMetricsEndpoint(APIView):
    def get(self, request, project_id):
        from apps.observability.runtime.metrics import runtime_metrics

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
