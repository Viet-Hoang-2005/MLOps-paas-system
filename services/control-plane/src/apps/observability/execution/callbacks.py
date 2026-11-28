from django.conf import settings
from django.core import signing
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.deployment.models import Build, Deployment
from apps.drift.models import DriftRun
from apps.observability.execution.argo_stops import (
    STOP_TOKEN_SALT,
    confirm_stop,
    project_has_unconfirmed_argo_stops,
    stop_identity,
)
from apps.observability.execution.observations import apply_observation
from apps.observability.execution.resources import ownership_for, resource_for


class ObservationSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["running", "completed", "failed", "not_found", "stopped", "error"])
    started_at = serializers.DateTimeField(required=False, allow_null=True)
    finished_at = serializers.DateTimeField(required=False, allow_null=True)
    never_started = serializers.BooleanField(required=False, default=False)
    error = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class ExecutionObservationEndpoint(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request, kind, public_id):
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        token_ttl = getattr(settings, "EXECUTION_OBSERVATION_TOKEN_TTL_SECONDS", 300)
        try:
            claims = signing.loads(token, salt="execution-observation", max_age=token_ttl)
        except signing.BadSignature:
            raise PermissionDenied("Invalid observation capability.")
        if claims.get("kind") != kind or claims.get("id") != str(public_id):
            raise PermissionDenied("Observation capability resource mismatch.")
        row = resource_for(kind, public_id)
        if not row:
            raise PermissionDenied("Observation resource no longer exists.")
        tenant, project_id = ownership_for(row, kind)
        if claims.get("project") != project_id or claims.get("tenant") != tenant:
            raise PermissionDenied("Observation capability ownership mismatch.")
        serializer = ObservationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = apply_observation(kind, public_id, claims["lease"], serializer.validated_data)
        if result == "ignored":
            raise PermissionDenied("Observation lease expired or was consumed.")
        return Response({"status": result})


class ArgoRuntimeStopEndpoint(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request, kind, public_id):
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        try:
            claims = signing.loads(token, salt=STOP_TOKEN_SALT, max_age=300)
        except signing.BadSignature:
            raise PermissionDenied("Invalid runtime stop capability.")
        if claims.get("kind") != kind or claims.get("resource_id") != str(public_id):
            raise PermissionDenied("Runtime stop capability resource mismatch.")
        if kind == "deployment":
            rows = Deployment.objects.filter(backend="argo").select_related("version__project__owner")
        elif kind == "drift":
            rows = DriftRun.objects.filter(monitor__backend="argo").select_related("monitor__version__project__owner")
        elif kind == "build":
            rows = Build.objects.filter(backend="argo").select_related("project__owner")
        else:
            raise PermissionDenied("Unsupported runtime kind.")
        resource = rows.filter(public_id=public_id).first()
        if not resource or claims != stop_identity(resource, kind):
            raise PermissionDenied("Runtime stop capability ownership mismatch.")
        serializer = ObservationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        status = serializer.validated_data["status"]
        if status == "stopped" and confirm_stop(resource, kind):
            _resume_stop(resource, kind)
        return Response({"status": status})


def _resume_stop(resource, kind):
    from apps.catalog.projects.tasks import execute_project_deletion
    from apps.deployment.builds.cleanup import cleanup_failed_build_artifacts, delete_build
    from apps.deployment.serving.rollout_tasks import stop_deployment
    from apps.drift.monitors.tasks import cleanup_drift_monitor_task
    from apps.registry.versions.tasks import cleanup_model_version

    if kind == "build":
        project = resource.project
    elif kind == "deployment":
        project = resource.version.project
    else:
        project = resource.monitor.version.project
    if project.deletion_state == "deleting":
        if not project_has_unconfirmed_argo_stops(project):
            execute_project_deletion.delay(str(project.public_id))
    elif kind == "build":
        if resource.deletion_state != "active":
            delete_build.delay(str(resource.public_id))
        elif resource.status in {"failed", "cancelled"}:
            cleanup_failed_build_artifacts.delay(str(resource.public_id), True)
    elif kind == "deployment":
        if resource.version.deletion_requested:
            cleanup_model_version.delay(str(resource.version.public_id))
        elif resource.status in {"stopped", "failed"}:
            stop_deployment.delay(str(resource.public_id))
    elif kind == "drift":
        if resource.monitor.version.deletion_requested:
            cleanup_model_version.delay(str(resource.monitor.version.public_id))
        elif resource.monitor.deletion_requested:
            cleanup_drift_monitor_task.delay(str(resource.monitor.public_id))
