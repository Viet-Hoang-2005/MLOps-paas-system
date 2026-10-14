import hashlib
import uuid

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from apps.access.models import UserAPIKey
from apps.catalog.models import ModelProject
from apps.training.models import TrainingJob, TrainingJobCapability


def _extract_bearer_token(request) -> str:
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    if auth_header.startswith("Basic "):
        import base64

        try:
            decoded = base64.b64decode(auth_header[6:].strip()).decode("utf-8")
            if ":" in decoded:
                return decoded.split(":", 1)[1]
            return decoded
        except Exception:
            pass
    return ""


def _is_job_active_for_mutation(job) -> tuple[bool, str]:
    """
    Check if a training job is currently active and eligible for updates/mutations.
    Returns (is_active: bool, error_message: str).
    """
    if not job:
        return False, "Job does not exist."
    if job.status in {"completed", "failed", "cancelled"}:
        return False, f"Job '{job.public_id}' is in terminal state ('{job.status}') and cannot be modified."
    if job.status == "cancelling" or getattr(job, "execution_stop_requested", False):
        return False, f"Job '{job.public_id}' is stopping/cancelling and cannot be modified."
    if getattr(job, "deletion_requested_at", None) is not None:
        return False, f"Job '{job.public_id}' is marked for deletion and cannot be modified."
    if getattr(job, "deletion_state", "active") != "active":
        return False, f"Job '{job.public_id}' is deleting and cannot be modified."
    if hasattr(job, "project") and getattr(job.project, "deletion_state", "active") != "active":
        return False, f"Project '{job.project.public_id}' is deleting and cannot be modified."
    return True, ""


def authenticate_mlflow_request(request):
    """
    Authenticate MLflow request:
    1. Capability token (tracking reporter): Issued to training job container
    2. UserAPIKey (mlp_...): External Data Scientist with API key
    3. User JWT / Session: Authenticated user via web or standard auth
    Returns: (job: TrainingJob | None, project: ModelProject | None, user, tenant_id: str, api_key: UserAPIKey | None)
    """
    token = _extract_bearer_token(request)

    # 1. Capability Token (Internal Training Container)
    if token and not token.startswith("mlp_"):
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        cap = (
            TrainingJobCapability.objects.filter(
                purpose="tracking",
                token_hash=token_hash,
                expires_at__gt=timezone.now(),
            )
            .select_related("job__project__owner")
            .first()
        )
        if cap:
            job = cap.job
            is_active, _ = _is_job_active_for_mutation(job)
            if not is_active:
                TrainingJobCapability.objects.filter(job=job, purpose="tracking").delete()
                return None, None, None, None, None
            project = job.project
            user = project.owner
            return job, project, user, user.tenant_id, None

    # 2. User API Key (External Data Scientist)
    if token and token.startswith("mlp_"):
        prefix = token[:16]
        api_key = (
            UserAPIKey.objects.filter(key_prefix=prefix, revoked_at__isnull=True)
            .select_related("user")
            .prefetch_related("allowed_projects")
            .first()
        )
        if api_key and api_key.matches(token):
            api_key.last_used_at = timezone.now()
            api_key.save(update_fields=["last_used_at"])
            user = api_key.user
            return None, None, user, user.tenant_id, api_key

    # 3. Standard Django User Authentication (Web session or Bearer JWT)
    if request.user and request.user.is_authenticated:
        user = request.user
        return None, None, user, getattr(user, "tenant_id", ""), None

    return None, None, None, None, None


def _require_auth(request):
    job, project, user, tenant_id, api_key = authenticate_mlflow_request(request)
    if not user or not tenant_id:
        return None, None, None, None, None, Response(
            {"error_code": "UNAUTHENTICATED", "message": "Valid tracking token, API key, or authentication is required."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    return job, project, user, tenant_id, api_key, None


def _is_project_allowed_for_api_key(api_key: UserAPIKey | None, project: ModelProject) -> bool:
    if api_key is None or not api_key.allowed_projects.exists():
        return True
    return api_key.allowed_projects.filter(id=project.id).exists()


def _scoped_projects_queryset(tenant_id: str, api_key: UserAPIKey | None = None):
    qs = ModelProject.objects.filter(owner__tenant_id=tenant_id, deletion_state="active")
    if api_key is not None and api_key.allowed_projects.exists():
        qs = qs.filter(id__in=api_key.allowed_projects.values_list("id", flat=True))
    return qs


def _resolve_target_job(job_from_auth, run_id_str, tenant_id, api_key=None, for_mutation=False):
    """
    Ensure run_id belongs to the authenticated tenant,
    strictly scopes capability tokens to their assigned job,
    restricts UserAPIKeys to their allowed_projects,
    and blocks mutations if the target job is stopped, terminal, or deleting.
    """
    if not run_id_str:
        if job_from_auth:
            job = job_from_auth
        else:
            return None, Response(
                {"error_code": "INVALID_PARAMETER_VALUE", "message": "Missing run_id"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    else:
        try:
            run_uuid = uuid.UUID(str(run_id_str))
        except (ValueError, TypeError):
            return None, Response(
                {"error_code": "INVALID_PARAMETER_VALUE", "message": f"Invalid run_id: {run_id_str}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 1. Tenant boundary check
        job = (
            TrainingJob.objects.filter(public_id=run_uuid, project__owner__tenant_id=tenant_id)
            .select_related("project__owner")
            .first()
        )
        if not job:
            return None, Response(
                {"error_code": "RESOURCE_DOES_NOT_EXIST", "message": f"Run '{run_id_str}' does not exist or unauthorized."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 2. Capability token strict scoping:
        # A capability token issued for Job A can NEVER access Job B, even within the same tenant.
        if job_from_auth is not None and job_from_auth.public_id != job.public_id:
            return None, Response(
                {"error_code": "PERMISSION_DENIED", "message": "Capability token is only authorized for its assigned job."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 3. UserAPIKey allowed_projects scoping
        if api_key is not None and not _is_project_allowed_for_api_key(api_key, job.project):
            return None, Response(
                {"error_code": "PERMISSION_DENIED", "message": "API key is not authorized for this project."},
                status=status.HTTP_403_FORBIDDEN,
            )

    if for_mutation:
        is_active, err_msg = _is_job_active_for_mutation(job)
        if not is_active:
            return None, Response(
                {"error_code": "INVALID_STATE", "message": err_msg},
                status=status.HTTP_400_BAD_REQUEST,
            )

    return job, None

