import base64
import uuid
from datetime import timedelta

import docker
import docker.errors
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.training.jobs.capabilities import issue_capability
from apps.training.jobs.storage_scope import validate_training_uri
from infrastructure.execution.argo_backend import _ArgoBackend
from infrastructure.execution.docker_client import DockerClient
from infrastructure.execution.docker_environment import _logging_environment
from infrastructure.storage import S3Storage


class ArgoTrainingBackend(_ArgoBackend):
    setting_name = "ARGO_TRAINING_WEBHOOK_URL"

    def run(self, job):
        runtime_name = f"training-{str(job.public_id).lower()}"
        validate_training_uri(job, self.storage.bucket, "code", job.code_snapshot_uri)
        training_data_uri = ""
        if job.input_contract != "workspace":
            validate_training_uri(job, self.storage.bucket, "data", job.data_snapshot_uri)
            training_data_uri = self.storage.presigned_get(
                job.data_snapshot_uri, settings.TRAINING_PRESIGNED_URL_TTL_SECONDS
            )
        validate_training_uri(job, self.storage.bucket, "output", job.output_uri)
        output_upload_capability = issue_capability(job, "output_upload", preserve_existing=True)
        reporter_capability = issue_capability(job, "trusted_reporter", preserve_existing=True)
        job.external_job_id = runtime_name
        job.tracking = {
            **job.tracking,
            "runtime": {
                "backend": "argo",
                "namespace": "mlops-paas-training",
                "train_job_name": runtime_name,
                "workflow_selector": f"mlops-paas.io/training-job-id={job.public_id}",
                "pod_selector": f"mlops-paas.io/training-job-id={job.public_id}",
            },
        }
        self.persist_dispatch(job, external_job_id=job.external_job_id, tracking=job.tracking)
        return self.trigger(
            {
                "job_id": str(job.public_id),
                "project_id": job.runtime_project_id,
                "tenant_id": job.owner.tenant_id,
                "input_contract": job.input_contract,
                "runtime_config_url": f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/training-jobs/{job.public_id}/runtime-config/",
                "runtime_config_capability": issue_capability(job, "runtime_config", preserve_existing=True),
                "job_name": runtime_name,
                "vcpu": job.vcpu,
                "memory": job.memory_mb,
                "max_runtime_seconds": job.max_runtime_seconds,
                "dispatch_timeout_seconds": settings.EXECUTION_DISPATCH_TIMEOUT_SECONDS,
                "input_download_url": f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/training-jobs/{job.public_id}/input-download-urls/",
                "input_download_capability": issue_capability(job, "input_download", preserve_existing=True),
                "accelerator_type": job.accelerator_type,
                "accelerator_count": job.accelerator_count,
                "accelerator_model": job.accelerator_model,
                "s3_source_uri": self.storage.presigned_get(
                    job.code_snapshot_uri, settings.TRAINING_PRESIGNED_URL_TTL_SECONDS
                ),
                "s3_training_data_uri": training_data_uri,
                "output_upload_url": (
                    f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/training-jobs/{job.public_id}/output-upload-url/"
                ),
                "output_upload_capability": output_upload_capability,
                "entry_point": job.entry_point,
                "model_flavor": job.model_flavor,
                "model_version": "",
                "requirements_text": job.requirements_text,
                "control_plane_webhook_url": (
                    f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/webhooks/training-jobs/{job.public_id}/"
                ),
                "reporter_capability": reporter_capability,
                "mlflow_tracking_uri": settings.CONTROL_PLANE_INTERNAL_URL,
                "mlflow_tracking_token": issue_capability(job, "tracking", preserve_existing=True),
            }
        )

    def cancel(self, job):
        with transaction.atomic():
            current = type(job).objects.select_for_update().get(pk=job.pk)
            if (
                current.status == "cancelled"
                and current.observation_status == "ok"
                and not current.execution_stop_requested
            ):
                return {"confirmed": True, "dispatched": False}
            if not (
                current.submitted_at
                or current.execution_deadline_at
                or current.status in {"queued", "running", "uploading", "cancelling"}
            ):
                return {"confirmed": True, "dispatched": False}

            now = timezone.now()
            if (
                current.execution_check_token
                and current.execution_check_lease_until
                and current.execution_check_lease_until > now
            ):
                # All observers share this lease. Keep in-flight callbacks valid while recording the stop intent.
                if not current.execution_stop_requested or current.observation_status != "cleanup_pending":
                    current.execution_stop_requested = True
                    current.observation_status = "cleanup_pending"
                    current.save(update_fields=["execution_stop_requested", "observation_status", "updated_at"])
                return {"confirmed": False, "dispatched": False}

            token = uuid.uuid4()
            lease = now + timedelta(seconds=settings.EXECUTION_CHECK_LEASE_SECONDS)
            current.execution_stop_requested = True
            current.observation_status = "cleanup_pending"
            current.execution_check_token = token
            current.execution_check_lease_until = lease
            current.next_execution_check_at = lease
            current.save(
                update_fields=[
                    "execution_stop_requested",
                    "observation_status",
                    "execution_check_token",
                    "execution_check_lease_until",
                    "next_execution_check_at",
                    "updated_at",
                ]
            )
        response = self.reconcile(current, "training", token, stop=True)
        return {"dispatched": True, "confirmed": False, "response": response}
class DockerTrainingBackend:
    def __init__(self, docker_client=None, storage=None):
        self.docker = docker_client or DockerClient(timeout=3)
        self.storage = storage or S3Storage()

    def run(self, job):
        if job.accelerator_type == "gpu":
            from apps.training.resources.local_gpu import require_device

            require_device(job.local_gpu_id, client=self.docker.client)
        validate_training_uri(job, self.storage.bucket, "code", job.code_snapshot_uri)
        training_data_uri = ""
        if job.input_contract != "workspace":
            validate_training_uri(job, self.storage.bucket, "data", job.data_snapshot_uri)
            training_data_uri = self.storage.presigned_get(
                job.data_snapshot_uri, settings.TRAINING_PRESIGNED_URL_TTL_SECONDS
            )
        validate_training_uri(job, self.storage.bucket, "output", job.output_uri)
        output_upload_capability = issue_capability(job, "output_upload", preserve_existing=True)
        environment = {
            **_logging_environment(),
            "S3_SOURCE_URI": self.storage.presigned_get(
                job.code_snapshot_uri, settings.TRAINING_PRESIGNED_URL_TTL_SECONDS
            ),
            "S3_TRAINING_DATA_URI": training_data_uri,
            "S3_OUTPUT_UPLOAD_URL": (
                f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/training-jobs/{job.public_id}/output-upload-url/"
            ),
            "S3_OUTPUT_UPLOAD_CAPABILITY": output_upload_capability,
            "S3_INPUT_DOWNLOAD_URL": f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/training-jobs/{job.public_id}/input-download-urls/",
            "S3_INPUT_DOWNLOAD_CAPABILITY": issue_capability(job, "input_download", preserve_existing=True),
            "MAX_RUNTIME_SECONDS": str(job.max_runtime_seconds),
            "ENTRY_POINT": job.entry_point,
            "MODEL_FLAVOR": job.model_flavor,
            "MODEL_VERSION": "",
            "TRAINING_JOB_ID": str(job.public_id),
            "TENANT_ID": job.owner.tenant_id,
            "REQUIREMENTS_TEXT": base64.b64encode(job.requirements_text.encode()).decode()
            if job.requirements_text
            else "",
            "REDIS_URL": settings.REDIS_URL,
            "MLFLOW_TRACKING_URI": settings.CONTROL_PLANE_INTERNAL_URL,
            "MLFLOW_TRACKING_TOKEN": issue_capability(job, "tracking", preserve_existing=True),
        }
        from .job_containers import start

        options = {}
        if job.input_contract == "workspace":
            from . import workspace_docker

            if not workspace_docker.prepare(self.docker.client, job, environment, settings.DOCKER_NETWORK_NAME):
                return {"dispatched": True, "preparing": True}
            environment.update(
                INPUT_CONTRACT="workspace",
                PREPARED_INPUT_DIR="/prepared/input",
                RUNTIME_CONFIG_URL=f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/training-jobs/{job.public_id}/runtime-config/",
                RUNTIME_CONFIG_CAPABILITY=issue_capability(job, "runtime_config", preserve_existing=True),
            )
            # Input tokens belong exclusively to the helper.
            for key in (
                "S3_SOURCE_URI",
                "S3_TRAINING_DATA_URI",
                "S3_INPUT_DOWNLOAD_URL",
                "S3_INPUT_DOWNLOAD_CAPABILITY",
            ):
                environment.pop(key, None)
            options = {
                "volumes": {workspace_docker.names(job)[1]: {"bind": "/prepared", "mode": "ro"}},
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
            }

        container = start(
            self.docker,
            job,
            "training",
            image="mlops-paas-training-runner:latest",
            name=f"training-{job.public_id}",
            environment=environment,
            network=settings.DOCKER_NETWORK_NAME,
            nano_cpus=job.vcpu * 1_000_000_000,
            mem_limit=f"{job.memory_mb}m",
            memswap_limit=f"{job.memory_mb}m",
            device_requests=[docker.types.DeviceRequest(device_ids=[job.local_gpu_id], capabilities=[["gpu"]])]
            if job.accelerator_type == "gpu"
            else [],
            **options,
        )
        return {"dispatched": True, "container_id": container.id}

    def poll(self, job):
        from .job_containers import observe

        result = observe(self.docker.client, job, "training")
        if job.input_contract == "workspace" and result["status"] == "not_found" and not job.external_job_id:
            from . import workspace_docker

            return workspace_docker.observe(self.docker.client, job)
        return result

    def cleanup(self, job):
        from .job_containers import remove

        result = remove(self.docker.client, job, "training")
        if job.input_contract == "workspace":
            from . import workspace_docker

            workspace_docker.cleanup(self.docker.client, job)
        return result

    def cancel(self, job):
        return {"dispatched": False, **self.cleanup(job)}
