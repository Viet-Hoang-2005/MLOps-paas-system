from apps.deployment.models import Endpoint
from apps.training.services.capabilities import issue_capability
from apps.training.services.storage_scope import validate_training_uri
from django.conf import settings

from infrastructure.argo import ArgoWebhookClient
from infrastructure.http import HttpClient
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import build_prefix, drift_run_prefix

from .image_references import (
    build_image_tag,
    image_repository,
    immutable_image_reference,
)


class _ArgoBackend:
    setting_name = ""

    def __init__(self, client=None, storage=None):
        self.client = client or ArgoWebhookClient()
        self.storage = storage or S3Storage()

    def trigger(self, payload):
        response = self.client.trigger(getattr(settings, self.setting_name), payload)
        return {"dispatched": True, "response": response}


class ArgoBuildBackend(_ArgoBackend):
    setting_name = "ARGO_BUILD_WEBHOOK_URL"

    def run(self, build):
        project = build.project
        source = build.input_assets.filter(kind__in=("source_artifact", "training_output")).first()
        if source is None and build.version_id:
            source = build.version.artifacts.filter(kind__in=("source", "training_output")).first()
        if not source:
            raise RuntimeError("The build has no source artifact.")
        source_uri = getattr(source, "s3_uri", "") or source.uri
        package_uri = (
            f"s3://{self.storage.bucket}/"
            f"{build_prefix(project.owner.tenant_id, project.public_id, build.public_id)}"
            "/artifacts/model-package.zip"
        )
        build.package_uri = package_uri
        build.save(update_fields=["package_uri", "updated_at"])
        return self.trigger(
            {
                "build_id": str(build.public_id),
                "project_id": str(project.public_id),
                "tenant_id": project.owner.tenant_id,
                "image_repository": image_repository(
                    project.public_id,
                    registry=settings.HARBOR_REGISTRY_URL,
                    registry_project=settings.HARBOR_USER_PROJECT,
                ),
                "image_tag": build_image_tag(build.public_id),
                "flavor": build.flavor,
                "task_type": "TEST_ZIP" if build.artifact_format == "mlflow_zip" else "BUILD",
                "requirements_text": build.requirements_snapshot,
                "source_artifact_name": source.name,
                "source_type": "training_job" if build.source_job_id else "manual_upload",
                "source_download_url": self.storage.presigned_get(source_uri, 14400),
                "output_upload_url": self.storage.presigned_put(package_uri, 14400),
                "control_plane_webhook_url": (
                    f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/webhooks/builds/{build.public_id}/"
                ),
            }
        )

    def cancel(self, build):
        return None


class ArgoTrainingBackend(_ArgoBackend):
    setting_name = "ARGO_TRAINING_WEBHOOK_URL"

    def run(self, job):
        runtime_name = f"training-{str(job.public_id).lower()}"
        validate_training_uri(job, self.storage.bucket, "code", job.code_snapshot_uri)
        validate_training_uri(job, self.storage.bucket, "data", job.data_snapshot_uri)
        validate_training_uri(job, self.storage.bucket, "output", job.output_uri)
        output_upload_capability = issue_capability(job, "output_upload")
        reporter_capability = issue_capability(job, "trusted_reporter")
        job.external_job_id = runtime_name
        job.tracking = {
            **job.tracking,
            "runtime": {
                "backend": "argo",
                "namespace": "user-jobs",
                "pytorch_job_name": runtime_name,
                "workflow_selector": f"mlops.io/training-job-id={job.public_id}",
                "pod_selector": f"mlops.io/training-job-id={job.public_id}",
            },
        }
        job.save(update_fields=["external_job_id", "tracking", "updated_at"])
        return self.trigger(
            {
                "job_id": str(job.public_id),
                "project_id": str(job.project.public_id),
                "tenant_id": job.project.owner.tenant_id,
                "job_name": runtime_name,
                "vcpu": job.vcpu,
                "memory": job.memory_mb,
                "accelerator_type": job.accelerator_type,
                "accelerator_count": job.accelerator_count,
                "s3_source_uri": self.storage.presigned_get(
                    job.code_snapshot_uri, settings.TRAINING_PRESIGNED_URL_TTL_SECONDS
                ),
                "s3_training_data_uri": self.storage.presigned_get(
                    job.data_snapshot_uri, settings.TRAINING_PRESIGNED_URL_TTL_SECONDS
                ),
                "output_upload_url": (
                    f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/training-jobs/{job.public_id}/output-upload-url/"
                ),
                "output_upload_capability": output_upload_capability,
                "entry_point": job.entry_point,
                "model_version": "",
                "requirements_text": job.requirements_text,
                "control_plane_webhook_url": (
                    f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/webhooks/training-jobs/{job.public_id}/"
                ),
                "reporter_capability": reporter_capability,
            }
        )

    def cancel(self, job):
        if settings.ARGO_CANCEL_TRAINING_WEBHOOK_URL:
            cancellation_capability = issue_capability(
                job,
                "cancel_reporter",
                ttl_seconds=min(600, settings.TRAINING_CAPABILITY_MAX_TTL_SECONDS),
            )
            response = self.client.trigger(
                settings.ARGO_CANCEL_TRAINING_WEBHOOK_URL,
                {
                    "job_id": str(job.public_id),
                    "job_name": job.external_job_id or f"training-{str(job.public_id).lower()}",
                    "control_plane_callback_url": (
                        f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/webhooks/"
                        f"training-jobs/{job.public_id}/cancellation/"
                    ),
                    "cancel_reporter_capability": cancellation_capability,
                },
            )
            return {"dispatched": True, "response": response}
        return None


class ArgoDeploymentBackend(_ArgoBackend):
    setting_name = "ARGO_DEPLOY_WEBHOOK_URL"

    def __init__(self, client=None, storage=None, http=None):
        super().__init__(client=client, storage=storage)
        self.http = http or HttpClient(timeout=(3.05, 10))
        self.log_sink = None

    def _log(self, message):
        if self.log_sink:
            self.log_sink(message)

    def deploy(self, deployment):
        version = deployment.version
        project = version.project
        container_name = f"deploy-{str(deployment.build.public_id).lower()}"
        model_type = "dl" if version.flavor in {"pytorch", "tensorflow"} else "ml"
        target_port = 3000 if model_type == "dl" else 5001
        self._log(f"Submitting Argo deployment workflow for runtime {container_name}.")
        self.trigger(
            {
                "deployment_id": str(deployment.public_id),
                "tenant_id": project.owner.tenant_id,
                "project_id": str(project.public_id),
                "model_version_id": str(version.public_id),
                "version": version.version,
                "image_uri": immutable_image_reference(deployment.build),
                "image_name": immutable_image_reference(deployment.build),
                "container_name": container_name,
                "model_type": model_type,
                "target_port": str(target_port),
                "model_uri": next(
                    (
                        artifact.uri
                        for artifact in version.artifacts.all()
                        if artifact.kind in {"source", "training_output"}
                    ),
                    "",
                ),
            }
        )
        self._log("Argo workflow submitted; waiting for the Kubernetes service health endpoint.")
        public_url = (
            f"{settings.MODEL_SERVER_PUBLIC_URL}/{project.owner.tenant_id}/models/"
            f"{project.public_id}/{version.public_id}"
        )
        return Endpoint.objects.update_or_create(
            deployment=deployment,
            defaults={
                "public_url": public_url,
                "internal_url": (
                    f"http://{container_name}-svc.{settings.MODEL_RUNTIME_NAMESPACE}.svc.cluster.local:"
                    f"{target_port}"
                ),
                "runtime_name": container_name,
                "runtime_namespace": settings.MODEL_RUNTIME_NAMESPACE,
                "health_status": "unknown",
            },
        )[0]

    def stop(self, deployment):
        endpoint = getattr(deployment, "endpoint", None)
        if endpoint and settings.ARGO_DELETE_WEBHOOK_URL:
            return self.client.trigger(settings.ARGO_DELETE_WEBHOOK_URL, {"container_name": endpoint.runtime_name})
        return None

    def health(self, deployment):
        endpoint = getattr(deployment, "endpoint", None)
        if not endpoint or not endpoint.internal_url:
            return False, {"status": "missing"}
        try:
            response = self.http.request("GET", f"{endpoint.internal_url}/health")
            payload = response.json()
            return bool(payload.get("model_loaded", True)), payload
        except Exception as exc:
            return False, {"status": "unhealthy", "detail": str(exc)}

    def logs(self, deployment):
        endpoint = getattr(deployment, "endpoint", None)
        return str(endpoint.metadata.get("logs", "")) if endpoint else ""


class ArgoDriftBackend(_ArgoBackend):
    setting_name = "ARGO_DRIFT_WEBHOOK_URL"

    def run(self, drift_run):
        monitor = drift_run.monitor
        project = monitor.version.project
        prefix = drift_run_prefix(
            project.owner.tenant_id,
            project.public_id,
            monitor.public_id,
            drift_run.public_id,
        )
        uris = {
            name: f"s3://{self.storage.bucket}/{prefix}{name}"
            for name in ("report.html", "report.json", "summary.json")
        }
        return self.trigger(
            {
                "job_id": str(drift_run.public_id),
                "monitor_id": str(monitor.public_id),
                "tenant_id": project.owner.tenant_id,
                "project_id": str(project.public_id),
                "model_version_id": str(monitor.version.public_id),
                "model_name": project.name,
                "model_uri": "",
                "reference_data_url": self.storage.presigned_get(monitor.reference_asset.s3_uri, 7200),
                "html_s3_uri": uris["report.html"],
                "report_json_s3_uri": uris["report.json"],
                "summary_json_s3_uri": uris["summary.json"],
                "html_public_url": "",
                "html_upload_url": self.storage.presigned_put(uris["report.html"], 7200, "text/html"),
                "report_json_upload_url": self.storage.presigned_put(uris["report.json"], 7200, "application/json"),
                "summary_json_upload_url": self.storage.presigned_put(uris["summary.json"], 7200, "application/json"),
                "control_plane_webhook_url": (
                    f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/webhooks/drift-runs/{drift_run.public_id}/"
                ),
            }
        )
