import hashlib
import io
import logging
import re
import tempfile
import uuid

from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.parsers import BaseParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ModelProject
from apps.training.models import TrainingJob, TrainingOutput
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import training_mlflow_artifacts_prefix
from ..auth import (
    _is_job_active_for_mutation,
    _is_project_allowed_for_api_key,
    _require_auth,
    _resolve_target_job,
)
from .runs import _mlflow_artifact_uri

logger = logging.getLogger(__name__)


def _bucket_name() -> str:
    return getattr(settings, "AWS_STORAGE_BUCKET_NAME", getattr(settings, "AWS_BUCKET_NAME", "mlops-paas-artifacts"))


class BinaryUploadParser(BaseParser):
    media_type = "*/*"

    def parse(self, stream, media_type=None, parser_context=None):
        # Return stream directly to enable chunked upload streaming without buffering entire file in RAM
        return stream


def _combine_effective_path(subpath: str, query_path: str | None) -> str:
    subpath = (subpath or "").strip().strip("/")
    if not query_path:
        return subpath
    query_path = query_path.strip().strip("/")
    if not subpath:
        return query_path
    if query_path.startswith("users/"):
        return query_path
    return f"{subpath}/{query_path}"


def _parse_artifact_path(subpath: str):
    """
    Parses subpath into (tenant_id, project_id, job_id, rel_path).
    Supports:
    1. Job-scoped paths (with or without 'mlflow/'):
       - users/<tenant>/models/<project>/training/jobs/<job>/mlflow/artifacts(/<rel_path>)?
       - users/<tenant>/models/<project>/training/jobs/<job>/artifacts(/<rel_path>)?
       - users/<tenant>/models/<project>/training/jobs/<job>(/<rel_path>)?
    2. Experiment-scoped paths:
       - users/<tenant>/models/<project>/training/jobs
       - users/<tenant>/models/<project>
    """
    clean = (subpath or "").strip().strip("/")

    # 1. Job-scoped path
    m_job = re.match(
        r"^users/([^/]+)/models/([^/]+)/training/jobs/([^/]+)(?:/(?:mlflow/)?artifacts)?(?:/(.*))?$",
        clean,
    )
    if m_job:
        tenant, project, job, rel = m_job.group(1), m_job.group(2), m_job.group(3), m_job.group(4)
        return tenant, project, job, rel or ""

    # 2. Experiment-scoped path
    m_exp = re.match(
        r"^users/([^/]+)/models/([^/]+)(?:/training/jobs)?$",
        clean,
    )
    if m_exp:
        return m_exp.group(1), m_exp.group(2), None, ""

    return None, None, None, clean


class MLflowArtifactsUploadUrlView(APIView):
    """Generates a presigned S3 PUT URL for uploading artifacts into tenant-isolated storage."""

    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        job_from_auth, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        run_id = request.data.get("run_id")
        artifact_path = request.data.get("path", "").strip().lstrip("/")
        if not artifact_path:
            return Response({"error_code": "INVALID_PARAMETER_VALUE", "message": "Path is required"}, status=status.HTTP_400_BAD_REQUEST)

        job, err_job = _resolve_target_job(job_from_auth, run_id, tenant_id, api_key=api_key, for_mutation=True)
        if err_job:
            return err_job

        bucket = _bucket_name()
        s3_key = f"{training_mlflow_artifacts_prefix(tenant_id, job.project.public_id, job.public_id)}{artifact_path}"
        storage = S3Storage()
        upload_url = storage.presigned_put(f"s3://{bucket}/{s3_key}", expires_in=3600)

        # Record output in TrainingOutput
        TrainingOutput.objects.update_or_create(
            job=job,
            relative_path=f"artifacts/{artifact_path}",
            defaults={
                "kind": "file",
                "s3_uri": f"s3://{bucket}/{s3_key}",
                "metadata": {"uploaded_via": "mlflow_log_artifact", "path": artifact_path},
            },
        )

        return Response({"upload_url": upload_url, "s3_uri": f"s3://{bucket}/{s3_key}"})


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
        job_from_auth, project_from_auth, user, auth_tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        query_path = request.query_params.get("path")
        effective_path = _combine_effective_path(subpath, query_path)
        path_tenant_id, path_project_id, path_job_id, rel_path = _parse_artifact_path(effective_path)

        if not path_tenant_id or not path_project_id or not path_job_id:
            return Response(
                {"error_code": "INVALID_PARAMETER_VALUE", "message": "Artifact upload requires a job-scoped path with a valid job ID."},
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
                job = TrainingJob.objects.filter(public_id=job_uuid, project__owner__tenant_id=auth_tenant_id).first()
            except (ValueError, TypeError):
                pass

        if not job:
            return Response(
                {"error_code": "RESOURCE_DOES_NOT_EXIST", "message": f"Job '{path_job_id}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if path_project_id and str(job.project.public_id) != path_project_id:
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
        s3_key = f"{training_mlflow_artifacts_prefix(auth_tenant_id, job.project.public_id, job.public_id)}{rel_path}"

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

        kind = "model" if rel_path.startswith("model") or rel_path.endswith((".pkl", ".pt", ".onnx", ".bin", ".h5")) else "file"

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

    def get(self, request, subpath=""):
        job_from_auth, project_from_auth, user, auth_tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        query_path = request.query_params.get("path")
        effective_path = _combine_effective_path(subpath, query_path)
        path_tenant_id, path_project_id, path_job_id, rel_path = _parse_artifact_path(effective_path)

        if not path_tenant_id or not path_project_id:
            return Response(
                {"error_code": "INVALID_PARAMETER_VALUE", "message": "Artifact URI must use the project-scoped or job-scoped MLflow path."},
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
                    {"error_code": "PERMISSION_DENIED", "message": "Capability token is only authorized for its assigned project."},
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
                job = TrainingJob.objects.filter(public_id=job_uuid, project__owner__tenant_id=auth_tenant_id).first()
            except (ValueError, TypeError):
                pass

        if not job:
            return Response(
                {"error_code": "RESOURCE_DOES_NOT_EXIST", "message": f"Job '{path_job_id}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if path_project_id and str(job.project.public_id) != path_project_id:
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
            s3_key = f"{training_mlflow_artifacts_prefix(auth_tenant_id, job.project.public_id, job.public_id)}{rel_path}"
            s3_uri = f"s3://{bucket}/{s3_key}"
            storage = S3Storage()

            # 1. Presigned download URL support if explicitly requested (?presigned=true)
            if request.query_params.get("presigned") == "true":
                try:
                    storage.head(s3_uri)
                    presigned_url = storage.presigned_get(s3_uri, expires_in=3600)
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
            sub = out.relative_path[len(prefix):]
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

    def delete(self, request, subpath=""):
        job_from_auth, project_from_auth, user, auth_tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        query_path = request.query_params.get("path")
        effective_path = _combine_effective_path(subpath, query_path)
        path_tenant_id, path_project_id, path_job_id, rel_path = _parse_artifact_path(effective_path)

        if not path_tenant_id or not path_project_id or not path_job_id:
            return Response(
                {"error_code": "INVALID_PARAMETER_VALUE", "message": "Artifact deletion requires a job-scoped path with a valid job ID."},
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
                job = TrainingJob.objects.filter(public_id=job_uuid, project__owner__tenant_id=auth_tenant_id).first()
            except (ValueError, TypeError):
                pass

        if not job:
            return Response(
                {"error_code": "RESOURCE_DOES_NOT_EXIST", "message": f"Job '{path_job_id}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if path_project_id and str(job.project.public_id) != path_project_id:
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
        storage = S3Storage()
        bucket = _bucket_name()

        if rel_path:
            s3_key = f"{training_mlflow_artifacts_prefix(auth_tenant_id, job.project.public_id, job.public_id)}{rel_path}"
            try:
                storage.delete(f"s3://{bucket}/{s3_key}")
            except Exception:
                pass
            try:
                storage.delete_prefix(f"{s3_key}/")
            except Exception:
                pass
            TrainingOutput.objects.filter(job=job, relative_path__startswith=f"artifacts/{rel_path}").delete()
        else:
            s3_prefix = training_mlflow_artifacts_prefix(auth_tenant_id, job.project.public_id, job.public_id)
            try:
                storage.delete_prefix(s3_prefix)
            except Exception:
                pass
            TrainingOutput.objects.filter(job=job, relative_path__startswith="artifacts/").delete()

        return Response({}, status=status.HTTP_200_OK)


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
            sub = out.relative_path[len(prefix):]
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

