import uuid

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.training.models import TrainingJobTag
from infrastructure.storage.paths import training_mlflow_artifacts_prefix
from ..auth import (
    _is_job_active_for_mutation,
    _require_auth,
    _resolve_target_job,
)


def _mlflow_artifact_uri(job):
    key = training_mlflow_artifacts_prefix(
        job.project.owner.tenant_id,
        job.project.public_id,
        job.public_id,
    ).rstrip("/")
    return f"mlflow-artifacts:/{key}"


class MLflowRunsCreateView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        job, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        # Creating an MLflow run via API key or external auth without an existing container job
        # creates an "orphan" TrainingJob with running status that never executes.
        # Disallow creating MLflow runs via API key. Runs must be initiated through the platform.
        if not job:
            return Response(
                {
                    "error_code": "PERMISSION_DENIED",
                    "message": "Creating MLflow runs via API key is disabled. Training jobs must be initiated through the MLOps platform.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        is_active, err_msg = _is_job_active_for_mutation(job)
        if not is_active:
            return Response(
                {"error_code": "INVALID_STATE", "message": err_msg},
                status=status.HTTP_400_BAD_REQUEST,
            )

        run_name = request.data.get("run_name") or "training-run"
        tags = request.data.get("tags") or []
        exp_id = request.data.get("experiment_id")

        target_job = job
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

        target_job.mlflow_run_id = str(target_job.public_id)
        target_job.save(update_fields=["mlflow_run_id", "updated_at"])

        # Persist tags
        for t in tags:
            k = str(t.get("key", "")).strip()[:160]
            v = str(t.get("value", ""))
            if k:
                TrainingJobTag.objects.update_or_create(job=target_job, name=k, defaults={"value": v})

        artifact_uri = _mlflow_artifact_uri(target_job)

        return Response(
            {
                "run": {
                    "info": {
                        "run_id": str(target_job.public_id),
                        "run_uuid": str(target_job.public_id),
                        "run_name": run_name or target_job.name,
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


class MLflowRunsUpdateView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        job_from_auth, project, user, tenant_id, api_key, err_resp = _require_auth(request)
        if err_resp:
            return err_resp

        run_id = request.data.get("run_id")
        job, err_job = _resolve_target_job(job_from_auth, run_id, tenant_id, api_key=api_key, for_mutation=True)
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

        artifact_uri = _mlflow_artifact_uri(job)

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

