import hashlib
import io
import logging
import tempfile
import uuid

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response

from apps.mlflow.artifacts.paths import _combine_effective_path, _parse_artifact_path
from apps.mlflow.auth import (
    _is_job_active_for_mutation,
    _is_project_allowed_for_api_key,
    _require_auth,
)
from apps.training.jobs.models import TrainingJob
from apps.training.jobs.storage_scope import training_prefix_for
from apps.training.outputs.models import TrainingOutput
from infrastructure.storage import S3Storage

logger = logging.getLogger(__name__)


def upload_artifact(request, subpath):
    job_from_auth, project_from_auth, user, auth_tenant_id, api_key, err_resp = _require_auth(request)
    if err_resp:
        return err_resp

    query_path = request.query_params.get("path")
    effective_path = _combine_effective_path(subpath, query_path)
    path_tenant_id, path_project_id, path_job_id, rel_path = _parse_artifact_path(effective_path)

    if not path_tenant_id or not path_job_id:
        return Response(
            {
                "error_code": "INVALID_PARAMETER_VALUE",
                "message": "Artifact upload requires a job-scoped path with a valid job ID.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if auth_tenant_id and path_tenant_id and auth_tenant_id != path_tenant_id:
        return Response(
            {"error_code": "PERMISSION_DENIED", "message": "Cross-tenant access forbidden."},
            status=status.HTTP_403_FORBIDDEN,
        )

    job = None
    if job_from_auth:
        if path_job_id and str(job_from_auth.public_id) != path_job_id:
            return Response(
                {"error_code": "PERMISSION_DENIED", "message": "Token not authorized for this job."},
                status=status.HTTP_403_FORBIDDEN,
            )
        job = job_from_auth
    elif path_job_id:
        try:
            job_uuid = uuid.UUID(str(path_job_id))
            job = TrainingJob.objects.filter(public_id=job_uuid, owner__tenant_id=auth_tenant_id).first()
        except (ValueError, TypeError):
            pass

    if not job:
        return Response(
            {"error_code": "RESOURCE_DOES_NOT_EXIST", "message": f"Job '{path_job_id}' not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if path_project_id and str(job.storage_project_id or "") != path_project_id:
        return Response(
            {"error_code": "PERMISSION_DENIED", "message": "Artifact path does not belong to this project."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if api_key is not None and not _is_project_allowed_for_api_key(api_key, job.project):
        return Response(
            {"error_code": "PERMISSION_DENIED", "message": "API key is not authorized for this project."},
            status=status.HTTP_403_FORBIDDEN,
        )

    is_active, err_msg = _is_job_active_for_mutation(job)
    if not is_active:
        return Response(
            {"error_code": "INVALID_STATE", "message": err_msg},
            status=status.HTTP_400_BAD_REQUEST,
        )

    rel_path = (rel_path or "").lstrip("/")
    if not rel_path:
        return Response(
            {"error_code": "INVALID_PARAMETER_VALUE", "message": "Artifact path is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    content_type = request.content_type or "application/octet-stream"
    s3_key = f"{training_prefix_for(job)}/mlflow/artifacts/{rel_path}"

    max_upload_size = getattr(settings, "MLFLOW_MAX_ARTIFACT_UPLOAD_SIZE_BYTES", 5 * 1024 * 1024 * 1024)

    # 1. Early Content-Length check if supplied by client
    cl_header = request.headers.get("Content-Length")
    if cl_header:
        try:
            cl = int(cl_header)
            if cl > max_upload_size:
                return Response(
                    {
                        "error_code": "MAX_SIZE_EXCEEDED",
                        "message": f"Artifact size ({cl} bytes) exceeds maximum allowed limit ({max_upload_size} bytes).",
                    },
                    status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                )
        except (ValueError, TypeError):
            pass

    data = request.data
    if isinstance(data, (bytes, bytearray)):
        stream = io.BytesIO(data)
    elif hasattr(data, "read"):
        stream = data
    else:
        stream = io.BytesIO(request.body or b"")

    # 2. Stream chunk-by-chunk through SpooledTemporaryFile (max 10 MiB in RAM, spills to disk for larger files)
    hasher = hashlib.sha256()
    size_bytes = 0
    chunk_size = 1024 * 1024  # 1 MiB chunks

    with tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024) as temp_file:
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            size_bytes += len(chunk)
            if size_bytes > max_upload_size:
                return Response(
                    {
                        "error_code": "MAX_SIZE_EXCEEDED",
                        "message": f"Artifact exceeds maximum allowed limit ({max_upload_size} bytes).",
                    },
                    status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                )
            hasher.update(chunk)
            temp_file.write(chunk)

        checksum = hasher.hexdigest()
        temp_file.seek(0)

        storage = S3Storage()
        stored = storage.upload_fileobj(
            fileobj=temp_file,
            key=s3_key,
            content_type=content_type,
            checksum=checksum,
            size_bytes=size_bytes,
        )

    kind = (
        "model"
        if rel_path.startswith("model") or rel_path.endswith((".pkl", ".pt", ".onnx", ".bin", ".h5"))
        else "file"
    )

    TrainingOutput.objects.update_or_create(
        job=job,
        relative_path=f"artifacts/{rel_path}",
        defaults={
            "kind": kind,
            "s3_uri": stored.uri,
            "checksum": stored.checksum,
            "size_bytes": stored.size_bytes,
            "content_type": content_type,
            "metadata": {"uploaded_via": "mlflow_proxy", "artifact_path": rel_path},
        },
    )

    return Response({}, status=status.HTTP_200_OK)
