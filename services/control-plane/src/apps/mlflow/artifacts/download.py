import logging
import uuid

from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.response import Response

from apps.catalog.models import ModelProject
from apps.mlflow.artifacts.paths import _bucket_name, _combine_effective_path, _parse_artifact_path
from apps.mlflow.auth import (
    _is_project_allowed_for_api_key,
    _require_auth,
)
from apps.training.jobs.models import TrainingJob
from apps.training.jobs.storage_scope import training_prefix_for
from apps.training.outputs.models import TrainingOutput
from infrastructure.storage import S3Storage

logger = logging.getLogger(__name__)


def download_artifact(request, subpath):
    job_from_auth, project_from_auth, user, auth_tenant_id, api_key, err_resp = _require_auth(request)
    if err_resp:
        return err_resp

    query_path = request.query_params.get("path")
    effective_path = _combine_effective_path(subpath, query_path)
    path_tenant_id, path_project_id, path_job_id, rel_path = _parse_artifact_path(effective_path)

    if not path_tenant_id or (not path_project_id and not path_job_id):
        return Response(
            {
                "error_code": "INVALID_PARAMETER_VALUE",
                "message": "Artifact URI must use the project-scoped or job-scoped MLflow path.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if auth_tenant_id and path_tenant_id and auth_tenant_id != path_tenant_id:
        return Response(
            {"error_code": "PERMISSION_DENIED", "message": "Cross-tenant access forbidden."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if not path_job_id:
        # Experiment-level artifact listing: list all jobs (runs) under this experiment
        try:
            proj_uuid = uuid.UUID(str(path_project_id))
            target_project = ModelProject.objects.filter(
                public_id=proj_uuid,
                owner__tenant_id=auth_tenant_id,
                deletion_state="active",
            ).first()
        except (ValueError, TypeError):
            target_project = None

        if not target_project:
            return Response(
                {"error_code": "RESOURCE_DOES_NOT_EXIST", "message": f"Experiment '{path_project_id}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if job_from_auth and job_from_auth.project_id != target_project.id:
            return Response(
                {
                    "error_code": "PERMISSION_DENIED",
                    "message": "Capability token is only authorized for its assigned project.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if api_key is not None and not _is_project_allowed_for_api_key(api_key, target_project):
            return Response(
                {"error_code": "PERMISSION_DENIED", "message": "API key is not authorized for this project."},
                status=status.HTTP_403_FORBIDDEN,
            )

        jobs = TrainingJob.objects.filter(project=target_project).order_by("-created_at")
        files_list = [{"path": str(j.public_id), "is_dir": True} for j in jobs]
        return Response({"files": files_list}, status=status.HTTP_200_OK)

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

    rel_path = (rel_path or "").strip().strip("/")
    is_explicit_listing = query_path is not None

    # Check if an exact matching file exists
    exact_output = None
    if not is_explicit_listing and rel_path:
        exact_output = TrainingOutput.objects.filter(job=job, relative_path=f"artifacts/{rel_path}").first()

    if exact_output or (not is_explicit_listing and "." in rel_path.split("/")[-1]):
        bucket = _bucket_name()
        s3_key = f"{training_prefix_for(job)}/mlflow/artifacts/{rel_path}"
        s3_uri = f"s3://{bucket}/{s3_key}"
        storage = S3Storage()

        # 1. Presigned download URL support if explicitly requested (?presigned=true)
        if request.query_params.get("presigned") == "true":
            try:
                storage.head(s3_uri)
                presigned_url = storage.presigned_get(s3_uri, expires_in=3600, public=job_from_auth is None)
                return Response({"download_url": presigned_url, "s3_uri": s3_uri}, status=status.HTTP_200_OK)
            except Exception as e:
                if isinstance(e, FileNotFoundError) or "NoSuchKey" in str(e) or "404" in str(e):
                    return Response(
                        {"error_code": "RESOURCE_DOES_NOT_EXIST", "message": f"Artifact '{rel_path}' not found."},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                return Response(
                    {"error_code": "INTERNAL_ERROR", "message": f"Failed to generate presigned URL: {e}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        # 2. Check existence and maximum download size limit
        max_download_size = getattr(settings, "MLFLOW_MAX_ARTIFACT_DOWNLOAD_SIZE_BYTES", 5 * 1024 * 1024 * 1024)
        try:
            head_obj = storage.head(s3_uri)
        except Exception as e:
            if isinstance(e, FileNotFoundError) or "NoSuchKey" in str(e) or "404" in str(e):
                return Response(
                    {"error_code": "RESOURCE_DOES_NOT_EXIST", "message": f"Artifact '{rel_path}' not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            logger.warning(f"Failed to inspect artifact {s3_key}: {e}")
            return Response(
                {"error_code": "INTERNAL_ERROR", "message": f"Failed to access artifact: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if head_obj.size_bytes > max_download_size:
            return Response(
                {
                    "error_code": "MAX_SIZE_EXCEEDED",
                    "message": f"Artifact size ({head_obj.size_bytes} bytes) exceeds maximum allowed limit ({max_download_size} bytes).",
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # 3. Stream download via StreamingHttpResponse without buffering entire file into RAM
        try:
            stream, content_len, s3_ct = storage.open_stream(s3_uri)
            content_type = (exact_output and exact_output.content_type) or s3_ct or "application/octet-stream"

            def stream_chunks():
                try:
                    if hasattr(stream, "iter_chunks"):
                        for chunk in stream.iter_chunks(chunk_size=1024 * 1024):
                            yield chunk
                    else:
                        while True:
                            chunk = stream.read(1024 * 1024)
                            if not chunk:
                                break
                            yield chunk
                finally:
                    if hasattr(stream, "close"):
                        stream.close()

            response = StreamingHttpResponse(stream_chunks(), content_type=content_type)
            if content_len is not None:
                response["Content-Length"] = str(content_len)
            elif head_obj.size_bytes:
                response["Content-Length"] = str(head_obj.size_bytes)
            return response
        except Exception as e:
            if isinstance(e, FileNotFoundError) or "NoSuchKey" in str(e) or "404" in str(e):
                return Response(
                    {"error_code": "RESOURCE_DOES_NOT_EXIST", "message": f"Artifact '{rel_path}' not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            logger.error(f"Failed to stream artifact {s3_key}: {e}")
            return Response(
                {"error_code": "INTERNAL_ERROR", "message": f"Failed to stream artifact: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # Directory listing
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
    return Response({"files": files_list}, status=status.HTTP_200_OK)
