from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.training.jobs.lifecycle import request_output_purge
from apps.training.jobs.selectors import job_for_user
from apps.training.jobs.serializers import TrainingJobSerializer
from apps.training.outputs.artifacts import get_job_reference_preview, get_model_output_summary, mutate_training_output


class TrainingOutputDownloadEndpoint(APIView):
    def get(self, request, job_id, output_id):
        from apps.training.jobs.snapshots import output_download

        return Response(output_download(job_for_user(request.user, job_id), output_id))


class TrainingWorkspaceDownloadEndpoint(APIView):
    def get(self, request, job_id, area):
        from django.http import FileResponse

        from apps.training.outputs.downloads import direct_workspace_download, workspace_download

        job = job_for_user(request.user, job_id)
        options = dict(
            area=area,
            path=request.query_params.get("path"),
            revision=request.query_params.get("revision"),
        )
        if request.query_params.get("delivery") == "direct":
            return direct_workspace_download(job, **options)
        stream, filename, content_type = workspace_download(job, **options)
        response = FileResponse(stream, as_attachment=True, filename=filename, content_type=content_type)
        response["Cache-Control"] = "private, no-store"
        return response


class TrainingJobModelOutputEndpoint(APIView):
    def get(self, request, job_id):
        job = job_for_user(request.user, job_id)
        return Response(get_model_output_summary(job))

    def patch(self, request, job_id):
        job = job_for_user(request.user, job_id)
        data = {
            "output_revision": request.data.get("output_revision"),
            "source_code_file": request.FILES.get("source_code_file"),
            "reference_data_file": request.FILES.get("reference_data_file"),
            "remove_assets": request.data.get("remove_assets"),
        }
        if "build_requirements_text" in request.data:
            data["build_requirements_text"] = request.data["build_requirements_text"]
        if "csv_upload_token" in request.data:
            data["csv_upload_token"] = request.data["csv_upload_token"]
        summary = mutate_training_output(job=job, user=request.user, data=data)
        return Response(summary, status=status.HTTP_200_OK)


class TrainingJobReferencePreviewEndpoint(APIView):
    def get(self, request, job_id):
        job = job_for_user(request.user, job_id)
        return Response(get_job_reference_preview(job))


class TrainingJobOutputsEndpoint(APIView):
    def delete(self, request, job_id):
        job = request_output_purge(job_for_user(request.user, job_id))
        return Response(TrainingJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)
