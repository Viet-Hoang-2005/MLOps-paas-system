from django.conf import settings
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.deployment.selectors import (
    build_for_user,
    builds_for_user,
    deployment_for_user,
    deployments_for_user,
    endpoint_for_user,
    endpoints_for_user,
)
from apps.deployment.services.builds import request_build_deletion, request_cancel, request_rebuild
from apps.deployment.services.deployments import endpoint_logs, request_deployment, request_stop
from apps.deployment.services.logs import build_logs, deployment_logs
from infrastructure.runtime_logs import runtime_log_page

from .serializers import BuildSerializer, DeploymentSerializer, EndpointSerializer


class BuildListEndpoint(generics.ListAPIView):
    serializer_class = BuildSerializer

    def get_queryset(self):
        return builds_for_user(self.request.user)


class BuildDetailEndpoint(generics.RetrieveDestroyAPIView):
    serializer_class = BuildSerializer
    lookup_field = "public_id"
    lookup_url_kwarg = "build_id"

    def get_queryset(self):
        return builds_for_user(self.request.user)

    def destroy(self, request, *args, **kwargs):
        build = request_build_deletion(self.get_object())
        return Response(BuildSerializer(build).data, status=status.HTTP_202_ACCEPTED)


class BuildRebuildEndpoint(APIView):
    def post(self, request, build_id):
        build = request_rebuild(build_for_user(request.user, build_id), backend=settings.BUILD_BACKEND)
        return Response(BuildSerializer(build).data, status=status.HTTP_201_CREATED)


class BuildRegisterEndpoint(APIView):
    def post(self, request, build_id):
        from apps.deployment.services.completion import request_registration

        build = request_registration(build_for_user(request.user, build_id))
        return Response(BuildSerializer(build).data, status=status.HTTP_202_ACCEPTED)


class BuildCancelEndpoint(APIView):
    def post(self, request, build_id):
        build = request_cancel(build_for_user(request.user, build_id))
        return Response(BuildSerializer(build).data, status=status.HTTP_202_ACCEPTED)


class BuildLogsEndpoint(APIView):
    def get(self, request, build_id):
        build = build_for_user(request.user, build_id)
        page = runtime_log_page(request, build, "build", build_logs)
        return Response(
            {
                "build_id": str(build.public_id),
                **page,
                "status": build.status,
                "error_message": build.error_message,
            }
        )


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


class EndpointListEndpoint(generics.ListAPIView):
    serializer_class = EndpointSerializer

    def get_queryset(self):
        return endpoints_for_user(self.request.user)


class EndpointLogsEndpoint(APIView):
    def get(self, request, endpoint_id):
        endpoint = endpoint_for_user(request.user, endpoint_id)
        return Response(
            {
                "endpoint_id": str(endpoint.public_id),
                "runtime_name": endpoint.runtime_name,
                "logs": endpoint_logs(endpoint),
            }
        )
