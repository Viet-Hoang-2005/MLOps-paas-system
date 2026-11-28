import logging

from rest_framework import status
from rest_framework.parsers import BaseParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.mlflow.artifacts.deletion import delete_artifact
from apps.mlflow.artifacts.download import download_artifact
from apps.mlflow.artifacts.upload import upload_artifact
from apps.mlflow.auth import (
    _require_auth,
    _resolve_target_job,
)
from apps.mlflow.runs import _mlflow_artifact_uri
from apps.training.outputs.models import TrainingOutput

logger = logging.getLogger(__name__)


class BinaryUploadParser(BaseParser):
    media_type = "*/*"

    def parse(self, stream, media_type=None, parser_context=None):
        # Return stream directly to enable chunked upload streaming without buffering entire file in RAM
        return stream


class MLflowArtifactsProxyView(APIView):
    """
    MLflow Standard Artifact Proxy View.
    Supports:
    - PUT: Upload artifact file (used by mlflow.log_artifact, mlflow.autolog)
    - GET: Download artifact file OR list directory artifacts (used by mlflow.download_artifacts, mlflow.list_artifacts)
    - DELETE: Delete artifact file/folder (used by mlflow.delete_artifacts)
    """

    parser_classes = (BinaryUploadParser,)
    authentication_classes = ()
    permission_classes = ()

    def put(self, request, subpath=""):
        return upload_artifact(request, subpath)

    def get(self, request, subpath=""):
        return download_artifact(request, subpath)

    def delete(self, request, subpath=""):
        return delete_artifact(request, subpath)


class MLflowArtifactsListView(APIView):
    """
    Standard MLflow REST API endpoint: GET /api/2.0/mlflow/artifacts/list?run_id=...&path=...
    """

    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        job_from_auth, project_from_auth, user, auth_tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        run_id = request.query_params.get("run_id") or request.query_params.get("run_uuid")
        job, err_job = _resolve_target_job(job_from_auth, run_id, auth_tenant_id, api_key=api_key)
        if err_job:
            return err_job

        rel_path = (request.query_params.get("path") or "").strip().strip("/")
        prefix = f"artifacts/{rel_path}".rstrip("/") + "/" if rel_path else "artifacts/"
        outputs = TrainingOutput.objects.filter(job=job, relative_path__startswith=prefix)
        items = {}
        for out in outputs:
            sub = out.relative_path[len(prefix) :]
            if not sub:
                continue
            parts = sub.split("/", 1)
            if len(parts) > 1:
                dir_name = parts[0]
                if dir_name not in items:
                    items[dir_name] = {"path": dir_name, "is_dir": True}
            else:
                file_name = parts[0]
                items[file_name] = {"path": file_name, "is_dir": False, "file_size": out.size_bytes}

        files_list = sorted(items.values(), key=lambda x: x["path"])
        root_uri = _mlflow_artifact_uri(job)
        return Response({"root_uri": root_uri, "files": files_list}, status=status.HTTP_200_OK)


class MLflowArtifactsMultipartFallbackView(APIView):
    """
    Handles /mlflow-artifacts/mpu/...
    When returning 501 with message "Multipart upload is not supported for the current artifact repository",
    MLflow client automatically falls back to single PUT upload.
    """

    authentication_classes = ()
    permission_classes = ()

    def _fallback(self):
        return Response(
            {
                "error_code": "NOT_IMPLEMENTED",
                "message": "Multipart upload is not supported for the current artifact repository",
            },
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )

    def get(self, request, subpath=""):
        return self._fallback()

    def post(self, request, subpath=""):
        return self._fallback()

    def put(self, request, subpath=""):
        return self._fallback()

    def delete(self, request, subpath=""):
        return self._fallback()
