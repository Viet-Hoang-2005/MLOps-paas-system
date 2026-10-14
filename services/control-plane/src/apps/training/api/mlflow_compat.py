import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import BaseParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access.models import UserAPIKey
from apps.catalog.models import ModelProject
from apps.training.models import (
    TrainingJob,
    TrainingJobCapability,
    TrainingJobMetric,
    TrainingJobParam,
    TrainingJobTag,
    TrainingOutput,
)
from common.redis_client import redis_client
from infrastructure.storage import S3Storage

logger = logging.getLogger(__name__)


def _bucket_name() -> str:
    return getattr(settings, "AWS_STORAGE_BUCKET_NAME", getattr(settings, "AWS_BUCKET_NAME", "mlops-paas-artifacts"))


class BinaryUploadParser(BaseParser):
    media_type = "*/*"

    def parse(self, stream, media_type=None, parser_context=None):
        return stream.read()


def _parse_artifact_path(subpath: str, job_from_auth=None, auth_tenant_id=None):
    clean = (subpath or "").strip().strip("/")
    # Pattern 1: tenants/<tenant_id>/jobs/<job_id>/artifacts/<rel_path>
    m = re.match(r"^tenants/([^/]+)/jobs/([^/]+)/artifacts(?:/(.*))?$", clean)
    if m:
        return m.group(1), m.group(2), m.group(3) or ""

    # Pattern 1a: tenants/<tenant_id>/projects/<project_id>/artifacts/<rel_path>
    m_proj = re.match(r"^tenants/([^/]+)/projects/([^/]+)/artifacts(?:/(.*))?$", clean)
    if m_proj:
        return m_proj.group(1), m_proj.group(2), m_proj.group(3) or ""

    # Pattern 2: jobs/<job_id>/artifacts/<rel_path>
    m = re.match(r"^jobs/([^/]+)/artifacts(?:/(.*))?$", clean)
    if m:
        return None, m.group(1), m.group(2) or ""

    # Pattern 3: <job_id>/artifacts/<rel_path>
    m = re.match(r"^([0-9a-fA-F-]{36})/artifacts(?:/(.*))?$", clean)
    if m:
        return None, m.group(1), m.group(2) or ""

    # Pattern 4: If capability token scoped to job_from_auth exists
    if job_from_auth is not None:
        if "artifacts/" in clean:
            rel = clean.split("artifacts/", 1)[1]
            return job_from_auth.project.owner.tenant_id, str(job_from_auth.public_id), rel
        return job_from_auth.project.owner.tenant_id, str(job_from_auth.public_id), clean

    # Fallback: check if clean has "artifacts/" anywhere
    if "artifacts/" in clean:
        prefix, rel = clean.split("artifacts/", 1)
        uuids = re.findall(r"[0-9a-fA-F-]{36}", prefix)
        if uuids:
            return None, uuids[-1], rel

    return None, None, clean


def _extract_bearer_token(request) -> str:
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    if auth_header.startswith("Basic "):
        # In case MLflow client sends basic auth, decode it
        import base64

        try:
            decoded = base64.b64decode(auth_header[6:].strip()).decode("utf-8")
            if ":" in decoded:
                return decoded.split(":", 1)[1]  # Use password/token part
            return decoded
        except Exception:
            pass
    return ""


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


def _resolve_target_job(job_from_auth, run_id_str, tenant_id, api_key=None):
    """
    Ensure run_id belongs to the authenticated tenant,
    strictly scopes capability tokens to their assigned job,
    and restricts UserAPIKeys to their allowed_projects.
    """
    if not run_id_str:
        if job_from_auth:
            return job_from_auth, None
        return None, Response(
            {"error_code": "INVALID_PARAMETER_VALUE", "message": "Missing run_id"},
            status=status.HTTP_400_BAD_REQUEST,
        )

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

    return job, None


class MLflowExperimentsGetByNameView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get_or_post(self, request):
        job, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        exp_name = request.query_params.get("experiment_name") or request.data.get("experiment_name") or ""
        target_project = project
        if not target_project:
            qs = _scoped_projects_queryset(tenant_id, api_key)
            if exp_name:
                target_project = qs.filter(name=exp_name).first()
            else:
                target_project = qs.first()

        if not target_project:
            if exp_name and api_key is not None and api_key.allowed_projects.exists():
                forbidden = ModelProject.objects.filter(owner__tenant_id=tenant_id, name=exp_name, deletion_state="active").first()
                if forbidden:
                    return Response(
                        {"error_code": "PERMISSION_DENIED", "message": "API key is not authorized for this experiment."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            return Response(
                {"error_code": "RESOURCE_DOES_NOT_EXIST", "message": f"Experiment '{exp_name}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if api_key is not None and not _is_project_allowed_for_api_key(api_key, target_project):
            return Response(
                {"error_code": "PERMISSION_DENIED", "message": "API key is not authorized for this experiment."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            {
                "experiment": {
                    "experiment_id": str(target_project.public_id),
                    "name": target_project.name,
                    "artifact_location": f"mlflow-artifacts:/tenants/{tenant_id}/projects/{target_project.public_id}/artifacts",
                    "lifecycle_stage": "active",
                    "tags": [{"key": "tenant_id", "value": tenant_id}],
                }
            }
        )

    def get(self, request):
        return self.get_or_post(request)

    def post(self, request):
        return self.get_or_post(request)


class MLflowExperimentsCreateView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        job, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        if job is not None:
            return Response(
                {"error_code": "PERMISSION_DENIED", "message": "Capability token cannot create new experiments."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if api_key is not None and api_key.allowed_projects.exists():
            return Response(
                {"error_code": "PERMISSION_DENIED", "message": "API key with restricted project scope cannot create new experiments."},
                status=status.HTTP_403_FORBIDDEN,
            )

        exp_name = request.data.get("name", "").strip() or "default-experiment"
        target_project = project or ModelProject.objects.filter(owner__tenant_id=tenant_id, name=exp_name, deletion_state="active").first()
        if not target_project:
            target_project = ModelProject.objects.filter(owner__tenant_id=tenant_id, deletion_state="active").first()

        if target_project:
            return Response({"experiment_id": str(target_project.public_id)})

        # Create a new project for this experiment if none exists
        new_project = ModelProject.objects.create(
            owner=user,
            name=exp_name,
            description=f"Auto-created experiment for tenant {tenant_id}",
        )
        return Response({"experiment_id": str(new_project.public_id)})


class MLflowExperimentsGetView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        job, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        exp_id = request.query_params.get("experiment_id") or ""
        target_project = None
        try:
            proj_uuid = uuid.UUID(str(exp_id))
            target_project = ModelProject.objects.filter(public_id=proj_uuid, owner__tenant_id=tenant_id).first()
        except (ValueError, TypeError):
            pass

        if not target_project:
            if not exp_id and job:
                target_project = job.project
            elif not exp_id:
                target_project = project or _scoped_projects_queryset(tenant_id, api_key).first()

        if not target_project:
            return Response(
                {"error_code": "RESOURCE_DOES_NOT_EXIST", "message": f"Experiment '{exp_id}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if job is not None and job.project_id != target_project.id:
            return Response(
                {"error_code": "PERMISSION_DENIED", "message": "Capability token is only authorized for its assigned experiment."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if api_key is not None and not _is_project_allowed_for_api_key(api_key, target_project):
            return Response(
                {"error_code": "PERMISSION_DENIED", "message": "API key is not authorized for this experiment."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            {
                "experiment": {
                    "experiment_id": str(target_project.public_id),
                    "name": target_project.name,
                    "artifact_location": f"mlflow-artifacts:/tenants/{tenant_id}/projects/{target_project.public_id}/artifacts",
                    "lifecycle_stage": "active",
                }
            }
        )


class MLflowRunsCreateView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        job, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        run_name = request.data.get("run_name") or "training-run"
        tags = request.data.get("tags") or []
        exp_id = request.data.get("experiment_id")

        # If this request comes from an existing containerized TrainingJob via capability token
        target_job = job
        if target_job:
            if exp_id:
                try:
                    proj_uuid = uuid.UUID(str(exp_id))
                    if target_job.project.public_id != proj_uuid:
                        return Response(
                            {"error_code": "PERMISSION_DENIED", "message": "Capability token cannot create runs in another experiment."},
                            status=status.HTTP_403_FORBIDDEN,
                        )
                except (ValueError, TypeError):
                    pass
        else:
            target_project = None
            if exp_id:
                try:
                    proj_uuid = uuid.UUID(str(exp_id))
                    target_project = (
                        ModelProject.objects.filter(public_id=proj_uuid, owner__tenant_id=tenant_id, deletion_state="active")
                        .first()
                    )
                except (ValueError, TypeError):
                    pass

            if not target_project:
                target_project = project or _scoped_projects_queryset(tenant_id, api_key).first()

            if not target_project:
                if api_key is not None and api_key.allowed_projects.exists():
                    return Response(
                        {"error_code": "PERMISSION_DENIED", "message": "API key is not authorized to create runs in this project."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                target_project = ModelProject.objects.create(
                    owner=user,
                    name="default-project",
                )

            # Check API key allowed_projects
            if api_key is not None and not _is_project_allowed_for_api_key(api_key, target_project):
                return Response(
                    {"error_code": "PERMISSION_DENIED", "message": "API key is not authorized for this project."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            target_job = TrainingJob.objects.create(
                project=target_project,
                name=run_name,
                model_flavor="sklearn",
                trigger_kind="manual",
                status="running",
                started_at=timezone.now(),
            )

        target_job.mlflow_run_id = str(target_job.public_id)
        target_job.save(update_fields=["mlflow_run_id", "updated_at"])

        # Persist tags
        for t in tags:
            k = str(t.get("key", "")).strip()[:160]
            v = str(t.get("value", ""))
            if k:
                TrainingJobTag.objects.update_or_create(job=target_job, name=k, defaults={"value": v})

        artifact_uri = f"mlflow-artifacts:/tenants/{tenant_id}/jobs/{target_job.public_id}/artifacts"

        return Response(
            {
                "run": {
                    "info": {
                        "run_id": str(target_job.public_id),
                        "run_uuid": str(target_job.public_id),
                        "run_name": target_job.name,
                        "experiment_id": str(target_job.project.public_id),
                        "status": "RUNNING",
                        "start_time": int((target_job.started_at or timezone.now()).timestamp() * 1000),
                        "artifact_uri": artifact_uri,
                        "lifecycle_stage": "active",
                    },
                    "data": {
                        "metrics": [],
                        "params": [],
                        "tags": tags,
                    },
                }
            }
        )


class MLflowRunsLogBatchView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        job_from_auth, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        run_id = request.data.get("run_id")
        job, err_job = _resolve_target_job(job_from_auth, run_id, tenant_id, api_key=api_key)
        if err_job:
            return err_job

        metrics = request.data.get("metrics") or []
        params = request.data.get("params") or []
        tags = request.data.get("tags") or []

        # 1. Bulk insert metrics
        metric_objects = []
        tracking_metrics_update = {}
        for m in metrics:
            k = str(m.get("key", "")).strip()[:160]
            try:
                val = float(m.get("value"))
            except (TypeError, ValueError):
                continue
            step = int(m.get("step") or 0)
            raw_ts = m.get("timestamp")
            ts = datetime.fromtimestamp(raw_ts / 1000.0, tz=dt_timezone.utc) if raw_ts else timezone.now()
            metric_objects.append(
                TrainingJobMetric(job=job, name=k, value=val, step=step, timestamp=ts)
            )
            tracking_metrics_update[k] = val

        if metric_objects:
            TrainingJobMetric.objects.bulk_create(metric_objects)

        # 2. Upsert params
        tracking_params_update = {}
        for p in params:
            k = str(p.get("key", "")).strip()[:160]
            v = str(p.get("value", ""))[:500]
            if k:
                TrainingJobParam.objects.update_or_create(job=job, name=k, defaults={"value": v})
                tracking_params_update[k] = v

        # 3. Upsert tags
        for t in tags:
            k = str(t.get("key", "")).strip()[:160]
            v = str(t.get("value", ""))[:500]
            if k:
                TrainingJobTag.objects.update_or_create(job=job, name=k, defaults={"value": v})

        # 4. Update job tracking summary
        if tracking_metrics_update or tracking_params_update:
            current_tracking = dict(job.tracking or {})
            if "metrics" not in current_tracking:
                current_tracking["metrics"] = {}
            if "params" not in current_tracking:
                current_tracking["params"] = {}
            current_tracking["metrics"].update(tracking_metrics_update)
            current_tracking["params"].update(tracking_params_update)
            job.tracking = current_tracking
            job.save(update_fields=["tracking", "updated_at"])

        # 5. Realtime emission to Redis
        try:
            r = redis_client(1)
            event_payload = json.dumps(
                {
                    "job_id": str(job.public_id),
                    "metrics": [{"key": m.name, "value": m.value, "step": m.step} for m in metric_objects[:50]],
                    "params": tracking_params_update,
                }
            )
            r.publish(f"training_metrics:{job.public_id}", event_payload)
            r.rpush(f"training_metric_events:{job.public_id}", event_payload)
            r.expire(f"training_metric_events:{job.public_id}", 86400 * 7)
        except Exception as exc:
            logger.warning("Failed to emit realtime metric event to Redis: %s", exc)

        return Response({})


class MLflowRunsLogMetricView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        job_from_auth, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        run_id = request.data.get("run_id")
        job, err_job = _resolve_target_job(job_from_auth, run_id, tenant_id, api_key=api_key)
        if err_job:
            return err_job

        key = str(request.data.get("key", "")).strip()[:160]
        try:
            val = float(request.data.get("value"))
        except (TypeError, ValueError):
            return Response({"error_code": "INVALID_PARAMETER_VALUE", "message": "Metric value must be float"}, status=status.HTTP_400_BAD_REQUEST)

        step = int(request.data.get("step") or 0)
        raw_ts = request.data.get("timestamp")
        ts = datetime.fromtimestamp(raw_ts / 1000.0, tz=dt_timezone.utc) if raw_ts else timezone.now()

        TrainingJobMetric.objects.create(job=job, name=key, value=val, step=step, timestamp=ts)

        current_tracking = dict(job.tracking or {})
        if "metrics" not in current_tracking:
            current_tracking["metrics"] = {}
        current_tracking["metrics"][key] = val
        job.tracking = current_tracking
        job.save(update_fields=["tracking", "updated_at"])

        return Response({})


class MLflowRunsLogParameterView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        job_from_auth, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        run_id = request.data.get("run_id")
        job, err_job = _resolve_target_job(job_from_auth, run_id, tenant_id, api_key=api_key)
        if err_job:
            return err_job

        key = str(request.data.get("key", "")).strip()[:160]
        value = str(request.data.get("value", ""))[:500]

        TrainingJobParam.objects.update_or_create(job=job, name=key, defaults={"value": value})

        current_tracking = dict(job.tracking or {})
        if "params" not in current_tracking:
            current_tracking["params"] = {}
        current_tracking["params"][key] = value
        job.tracking = current_tracking
        job.save(update_fields=["tracking", "updated_at"])

        return Response({})


class MLflowRunsSetTagView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        job_from_auth, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        run_id = request.data.get("run_id")
        job, err_job = _resolve_target_job(job_from_auth, run_id, tenant_id, api_key=api_key)
        if err_job:
            return err_job

        key = str(request.data.get("key", "")).strip()[:160]
        value = str(request.data.get("value", ""))[:500]

        TrainingJobTag.objects.update_or_create(job=job, name=key, defaults={"value": value})
        return Response({})


class MLflowRunsUpdateView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        job_from_auth, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        run_id = request.data.get("run_id")
        job, err_job = _resolve_target_job(job_from_auth, run_id, tenant_id, api_key=api_key)
        if err_job:
            return err_job

        status_str = str(request.data.get("status", "")).upper()
        end_time = request.data.get("end_time")

        current_tracking = dict(job.tracking or {})
        if status_str:
            current_tracking["mlflow_status"] = status_str
        if end_time is not None:
            current_tracking["end_time"] = end_time
        job.tracking = current_tracking
        job.save(update_fields=["tracking", "updated_at"])

        mlflow_status = status_str or current_tracking.get("mlflow_status") or "FINISHED"

        return Response(
            {
                "run_info": {
                    "run_id": str(job.public_id),
                    "status": mlflow_status,
                }
            }
        )


class MLflowRunsGetView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        job_from_auth, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        run_id = request.query_params.get("run_id")
        job, err_job = _resolve_target_job(job_from_auth, run_id, tenant_id, api_key=api_key)
        if err_job:
            return err_job

        # Query all latest metrics
        metrics_list = []
        for name in job.step_metrics.values_list("name", flat=True).distinct():
            latest = job.step_metrics.filter(name=name).order_by("-step", "-created_at").first()
            if latest:
                metrics_list.append(
                    {
                        "key": latest.name,
                        "value": latest.value,
                        "step": latest.step,
                        "timestamp": int(latest.timestamp.timestamp() * 1000) if latest.timestamp else 0,
                    }
                )

        params_list = [{"key": p.name, "value": p.value} for p in job.hyperparameters.all()]
        tags_list = [{"key": t.name, "value": t.value} for t in job.tags.all()]

        artifact_uri = f"mlflow-artifacts:/tenants/{tenant_id}/jobs/{job.public_id}/artifacts"

        current_tracking = dict(job.tracking or {})
        mlflow_status = current_tracking.get("mlflow_status") or (
            "FINISHED" if job.status == "completed" else "RUNNING" if job.status == "running" else job.status.upper()
        )
        end_time = current_tracking.get("end_time") or (int(job.completed_at.timestamp() * 1000) if job.completed_at else None)

        return Response(
            {
                "run": {
                    "info": {
                        "run_id": str(job.public_id),
                        "run_uuid": str(job.public_id),
                        "run_name": job.name,
                        "experiment_id": str(job.project.public_id),
                        "status": mlflow_status,
                        "start_time": int((job.started_at or timezone.now()).timestamp() * 1000),
                        "end_time": end_time,
                        "artifact_uri": artifact_uri,
                        "lifecycle_stage": "active",
                    },
                    "data": {
                        "metrics": metrics_list,
                        "params": params_list,
                        "tags": tags_list,
                    },
                }
            }
        )


class MLflowMetricsGetHistoryView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        job_from_auth, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        run_id = request.query_params.get("run_id")
        metric_key = request.query_params.get("metric_key") or ""
        job, err_job = _resolve_target_job(job_from_auth, run_id, tenant_id, api_key=api_key)
        if err_job:
            return err_job

        points = job.step_metrics.filter(name=metric_key).order_by("step")
        return Response(
            {
                "metrics": [
                    {
                        "key": p.name,
                        "value": p.value,
                        "step": p.step,
                        "timestamp": int(p.timestamp.timestamp() * 1000) if p.timestamp else 0,
                    }
                    for p in points
                ]
            }
        )


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

        job, err_job = _resolve_target_job(job_from_auth, run_id, tenant_id, api_key=api_key)
        if err_job:
            return err_job

        bucket = _bucket_name()
        s3_key = f"tenants/{tenant_id}/jobs/{job.public_id}/artifacts/{artifact_path}"
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

        subpath = subpath or request.query_params.get("path") or ""
        path_tenant_id, path_job_id, rel_path = _parse_artifact_path(
            subpath, job_from_auth=job_from_auth, auth_tenant_id=auth_tenant_id
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

        if api_key is not None and not _is_project_allowed_for_api_key(api_key, job.project):
            return Response(
                {"error_code": "PERMISSION_DENIED", "message": "API key is not authorized for this project."},
                status=status.HTTP_403_FORBIDDEN,
            )

        rel_path = (rel_path or "").lstrip("/")
        if not rel_path:
            return Response(
                {"error_code": "INVALID_PARAMETER_VALUE", "message": "Artifact path is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = request.data if isinstance(request.data, (bytes, bytearray)) else (request.body or b"")
        content_type = request.content_type or "application/octet-stream"

        bucket = _bucket_name()
        s3_key = f"tenants/{auth_tenant_id}/jobs/{job.public_id}/artifacts/{rel_path}"

        storage = S3Storage()
        stored = storage.put(key=s3_key, body=payload, content_type=content_type)

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
        effective_path = query_path if query_path is not None else subpath
        path_tenant_id, path_job_id, rel_path = _parse_artifact_path(
            effective_path, job_from_auth=job_from_auth, auth_tenant_id=auth_tenant_id
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
            s3_key = f"tenants/{auth_tenant_id}/jobs/{job.public_id}/artifacts/{rel_path}"
            storage = S3Storage()
            try:
                data = storage.read(f"s3://{bucket}/{s3_key}", max_bytes=500 * 1024 * 1024)
                content_type = exact_output.content_type if exact_output and exact_output.content_type else "application/octet-stream"
                response = HttpResponse(data, content_type=content_type)
                response["Content-Length"] = len(data)
                return response
            except Exception as e:
                logger.warning(f"Failed to read artifact {s3_key}: {e}")
                return Response(
                    {"error_code": "RESOURCE_DOES_NOT_EXIST", "message": f"Artifact '{rel_path}' not found."},
                    status=status.HTTP_404_NOT_FOUND,
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

        subpath = subpath or request.query_params.get("path") or ""
        path_tenant_id, path_job_id, rel_path = _parse_artifact_path(
            subpath, job_from_auth=job_from_auth, auth_tenant_id=auth_tenant_id
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

        if api_key is not None and not _is_project_allowed_for_api_key(api_key, job.project):
            return Response(
                {"error_code": "PERMISSION_DENIED", "message": "API key is not authorized for this project."},
                status=status.HTTP_403_FORBIDDEN,
            )

        rel_path = (rel_path or "").lstrip("/")
        storage = S3Storage()
        bucket = _bucket_name()

        if rel_path:
            s3_key = f"tenants/{auth_tenant_id}/jobs/{job.public_id}/artifacts/{rel_path}"
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
            s3_prefix = f"tenants/{auth_tenant_id}/jobs/{job.public_id}/artifacts/"
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
        root_uri = f"mlflow-artifacts:/tenants/{auth_tenant_id}/jobs/{job.public_id}/artifacts"
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

