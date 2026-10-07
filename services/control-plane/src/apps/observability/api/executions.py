from django.core import signing
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.observability.services.executions import apply_observation, project_for, resource_for


class ObservationSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["running", "completed", "failed", "not_found", "stopped", "error"])
    started_at = serializers.DateTimeField(required=False, allow_null=True)
    finished_at = serializers.DateTimeField(required=False, allow_null=True)
    error = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class ExecutionObservationEndpoint(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request, kind, public_id):
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        try:
            claims = signing.loads(token, salt="execution-observation", max_age=60)
        except signing.BadSignature:
            raise PermissionDenied("Invalid observation capability.")
        if claims.get("kind") != kind or claims.get("id") != str(public_id):
            raise PermissionDenied("Observation capability resource mismatch.")
        row = resource_for(kind, public_id)
        if not row:
            raise PermissionDenied("Observation resource no longer exists.")
        project = project_for(row, kind)
        if claims.get("project") != str(project.public_id) or claims.get("tenant") != str(project.owner.tenant_id):
            raise PermissionDenied("Observation capability ownership mismatch.")
        serializer = ObservationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = apply_observation(kind, public_id, claims["lease"], serializer.validated_data)
        if result == "ignored":
            raise PermissionDenied("Observation lease expired or was consumed.")
        return Response({"status": result})
