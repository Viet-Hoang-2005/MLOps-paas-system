import logging
import uuid

from rest_framework import status
from rest_framework.response import Response

from apps.mlflow.artifacts.paths import _bucket_name, _combine_effective_path, _parse_artifact_path
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


def delete_artifact(request, subpath):
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
                "message": "Artifact deletion requires a job-scoped path with a valid job ID.",
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
    storage = S3Storage()
    bucket = _bucket_name()

    if rel_path:
        s3_key = f"{training_prefix_for(job)}/mlflow/artifacts/{rel_path}"
        try:
            storage.delete(f"s3://{bucket}/{s3_key}")
        except Exception:
            pass
        try:
            storage.delete_prefix(f"{s3_key}/")
        except Exception:
            pass
        from django.db.models import Q

        target = f"artifacts/{rel_path}"
        TrainingOutput.objects.filter(job=job).filter(
            Q(relative_path=target) | Q(relative_path__startswith=f"{target}/")
        ).delete()
    else:
        s3_prefix = training_prefix_for(job) + "/mlflow/artifacts/"
        try:
            storage.delete_prefix(s3_prefix)
        except Exception:
            pass
        TrainingOutput.objects.filter(job=job, relative_path__startswith="artifacts/").delete()

    return Response({}, status=status.HTTP_200_OK)
