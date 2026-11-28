from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.registry.versions.selectors import version_for_user
from apps.training.jobs.selectors import job_for_user
from apps.training.workspace.models import TrainingWorkspace
from common.api.exceptions import Conflict
from common.validation.artifacts import MAX_REFERENCE_DATA_BYTES
from infrastructure.storage.staged_csv import issue_csv_upload


class CSVUploadRequest(serializers.Serializer):
    filename = serializers.CharField(max_length=255)
    size_bytes = serializers.IntegerField(min_value=1, max_value=MAX_REFERENCE_DATA_BYTES)
    revision = serializers.IntegerField(min_value=1, required=False)


class CSVUploadURLEndpoint(APIView):
    def post(self, request, purpose, resource_id):
        serializer = CSVUploadRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        revision = data.get("revision")
        if purpose == "workspace":
            resource = get_object_or_404(TrainingWorkspace, public_id=resource_id, owner=request.user)
            if revision != resource.revision or resource.deletion_requested_at or resource.active_jobs().exists():
                raise Conflict("This workspace is read-only or its revision changed.")
        elif purpose == "training-output":
            resource = job_for_user(request.user, resource_id)
            if (
                revision != resource.output_revision or resource.status != "completed"
                or resource.outputs_purged_at or resource.deletion_requested_at
                or (resource.project and resource.project.deletion_state != "active")
            ):
                raise Conflict("Training output is unavailable or its revision changed.")
        elif purpose in {"version", "drift-monitor"}:
            resource = version_for_user(request.user, resource_id)
            project = resource.project
            if resource.deletion_requested or project.deletion_state != "active" or not project.is_active:
                raise Conflict("This model version is unavailable.")
            if resource.artifacts.filter(kind="reference_data").exists():
                raise Conflict("This version already has reference data.")
            if purpose == "drift-monitor" and (
                not project.active_deployment_id
                or project.active_deployment.version_id != resource.pk
                or project.active_deployment.status != "succeeded"
            ):
                raise Conflict("Select the project's Running version. Reload if deployment changed.")
            revision = None
        else:
            raise NotFound()
        result = issue_csv_upload(
            resource, purpose, filename=data["filename"], size=data["size_bytes"], revision=revision
        )
        return Response(result, headers={"Cache-Control": "private, no-store"})
