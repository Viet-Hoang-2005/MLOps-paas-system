import uuid

from django.db.models import F, Window
from django.db.models.functions import RowNumber
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.mlflow.auth import _is_job_active_for_mutation, _require_auth, _resolve_target_job
from apps.training.jobs.models import TrainingJobTag
from apps.training.jobs.storage_scope import training_prefix_for


def _mlflow_artifact_uri(job):
    key = training_prefix_for(job) + "/mlflow/artifacts"
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

        tags = request.data.get("tags") or []
        exp_id = request.data.get("experiment_id")

        target_job = job
        if exp_id:
            try:
                proj_uuid = uuid.UUID(str(exp_id))
                if (target_job.storage_project_id or target_job.public_id) != proj_uuid:
                    return Response(
                        {
                            "error_code": "PERMISSION_DENIED",
                            "message": "Capability token cannot create runs in another experiment.",
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
            except (ValueError, TypeError):
                pass

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
                        "run_name": str(target_job.public_id),
                        "experiment_id": str(target_job.storage_project_id or target_job.public_id),
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

        if status_str:
            TrainingJobTag.objects.update_or_create(
                job=job, name="mlflow.runStatus", defaults={"value": status_str[:500]}
            )
        if end_time is not None:
            TrainingJobTag.objects.update_or_create(
                job=job, name="mlflow.endTime", defaults={"value": str(end_time)[:500]}
            )

        mlflow_status = (
            status_str
            or TrainingJobTag.objects.filter(job=job, name="mlflow.runStatus")
            .values_list("value", flat=True)
            .first()
            or "FINISHED"
        )

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

        latest_metrics = (
            job.step_metrics.annotate(
                rank=Window(
                    expression=RowNumber(),
                    partition_by=[F("name")],
                    order_by=[F("step").desc(), F("created_at").desc(), F("pk").desc()],
                )
            )
            .filter(rank=1)
            .order_by("name")
            .values_list("name", "value", "step", "timestamp")
        )
        metrics_list = [
            {
                "key": name,
                "value": value,
                "step": step,
                "timestamp": int(timestamp.timestamp() * 1000) if timestamp else 0,
            }
            for name, value, step, timestamp in latest_metrics
        ]

        params_list = [{"key": p.name, "value": p.value} for p in job.hyperparameters.all()]
        tags_list = [{"key": t.name, "value": t.value} for t in job.tags.all()]
        tags_map = {t["key"]: t["value"] for t in tags_list}

        artifact_uri = _mlflow_artifact_uri(job)

        mlflow_status = tags_map.get("mlflow.runStatus") or (
            "FINISHED" if job.status == "completed" else "RUNNING" if job.status == "running" else job.status.upper()
        )
        raw_end = tags_map.get("mlflow.endTime")
        end_time = int(raw_end) if raw_end and raw_end.isdigit() else (
            int(job.completed_at.timestamp() * 1000) if job.completed_at else None
        )

        return Response(
            {
                "run": {
                    "info": {
                        "run_id": str(job.public_id),
                        "run_uuid": str(job.public_id),
                        "run_name": str(job.public_id),
                        "experiment_id": str(job.storage_project_id or job.public_id),
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
