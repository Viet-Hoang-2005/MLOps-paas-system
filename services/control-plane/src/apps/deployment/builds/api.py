from django.conf import settings
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.deployment.builds.selectors import build_for_user, builds_for_user
from apps.deployment.builds.serializers import BuildSerializer
from apps.deployment.builds.submission import request_build_deletion, request_cancel, request_rebuild
from apps.deployment.execution.logs import build_logs
from infrastructure.telemetry.runtime_logs import runtime_log_page


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
        from apps.deployment.builds.registration import request_registration

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
