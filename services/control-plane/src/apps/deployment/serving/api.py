from django.conf import settings
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.deployment.execution.logs import deployment_logs
from apps.deployment.serving.rollout import request_deployment, request_stop
from apps.deployment.serving.selectors import deployment_for_user, deployments_for_user
from apps.deployment.serving.serializers import DeploymentSerializer
from infrastructure.telemetry.runtime_logs import runtime_log_page


class DeploymentListCreateEndpoint(generics.ListCreateAPIView):
    serializer_class = DeploymentSerializer

    def get_queryset(self):
        return deployments_for_user(self.request.user)

    def perform_create(self, serializer):
        build = serializer.validated_data["build"]
        serializer.instance = request_deployment(build, settings.DEPLOYMENT_BACKEND)


class DeploymentDetailEndpoint(generics.RetrieveAPIView):
    serializer_class = DeploymentSerializer
    lookup_field = "public_id"
    lookup_url_kwarg = "deployment_id"

    def get_queryset(self):
        return deployments_for_user(self.request.user)


class DeploymentStopEndpoint(APIView):
    def post(self, request, deployment_id):
        deployment = request_stop(deployment_for_user(request.user, deployment_id))
        return Response(DeploymentSerializer(deployment).data, status=status.HTTP_202_ACCEPTED)


class DeploymentLogsEndpoint(APIView):
    def get(self, request, deployment_id):
        deployment = deployment_for_user(request.user, deployment_id)
        page = runtime_log_page(request, deployment, "deployment", deployment_logs)
        return Response(
            {
                "deployment_id": str(deployment.public_id),
                **page,
                "status": deployment.status,
                "error_message": deployment.error_message,
            }
        )


class DeploymentRuntimeLogsEndpoint(APIView):
    def get(self, request, deployment_id):
        from apps.deployment.serving.runtime_logs import docker_runtime_page
        from infrastructure.telemetry.runtime_logs import uses_loki

        deployment = deployment_for_user(request.user, deployment_id)
        if uses_loki(deployment.backend):
            page = runtime_log_page(request, deployment, "deployment_runtime", lambda *_: ([], 0))
        elif deployment.backend == "docker":
            page = docker_runtime_page(request, deployment)
        else:
            page = {"logs": [], "next_offset": 0, "log_error": "unavailable"}
        return Response({"deployment_id": str(deployment.public_id), **page, "status": deployment.status})
