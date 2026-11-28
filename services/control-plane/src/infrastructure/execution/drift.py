import os

from django.conf import settings

from infrastructure.execution.argo_backend import _ArgoBackend
from infrastructure.execution.docker_client import DockerClient
from infrastructure.execution.docker_environment import _logging_environment
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import drift_run_prefix


class ArgoDriftBackend(_ArgoBackend):
    setting_name = "ARGO_DRIFT_WEBHOOK_URL"

    def cancel(self, drift_run):
        return self.request_runtime_stop(drift_run, "drift")

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
        drift_run.report_html_uri = uris["report.html"]
        drift_run.report_json_uri = uris["report.json"]
        drift_run.summary_uri = uris["summary.json"]
        self.persist_dispatch(
            drift_run,
            report_html_uri=drift_run.report_html_uri,
            report_json_uri=drift_run.report_json_uri,
            summary_uri=drift_run.summary_uri,
        )
        return self.trigger(
            {
                "job_id": str(drift_run.public_id),
                "max_runtime_seconds": settings.DRIFT_MAX_RUNTIME_SECONDS,
                "dispatch_timeout_seconds": settings.EXECUTION_DISPATCH_TIMEOUT_SECONDS,
                "monitor_id": str(monitor.public_id),
                "tenant_id": project.owner.tenant_id,
                "project_id": str(project.public_id),
                "model_version_id": str(monitor.version.public_id),
                "model_name": project.name,
                "reference_data_url": self.storage.presigned_get(monitor.reference_uri, 7200),
                "html_s3_uri": uris["report.html"],
                "report_json_s3_uri": uris["report.json"],
                "summary_json_s3_uri": uris["summary.json"],
                "html_upload_url": self.storage.presigned_put(uris["report.html"], 7200, "text/html"),
                "report_json_upload_url": self.storage.presigned_put(uris["report.json"], 7200, "application/json"),
                "summary_json_upload_url": self.storage.presigned_put(uris["summary.json"], 7200, "application/json"),
                "control_plane_webhook_url": (
                    f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/webhooks/drift-runs/{drift_run.public_id}/"
                ),
                "control_plane_internal_url": settings.CONTROL_PLANE_INTERNAL_URL,
            }
        )
class DockerDriftBackend:
    def __init__(self, docker_client=None, storage=None):
        self.docker = docker_client or DockerClient(timeout=3)
        self.storage = storage or S3Storage()

    def run(self, drift_run):
        monitor = drift_run.monitor
        project = monitor.version.project
        prefix = drift_run_prefix(project.owner.tenant_id, project.public_id, monitor.public_id, drift_run.public_id)
        uris = {
            name: f"s3://{self.storage.bucket}/{prefix}{name}"
            for name in ("report.html", "report.json", "summary.json")
        }
        environment = {
            **_logging_environment(),
            "JOB_ID": str(drift_run.public_id),
            "TENANT_ID": project.owner.tenant_id,
            "PROJECT_ID": str(project.public_id),
            "MODEL_VERSION_ID": str(monitor.version.public_id),
            "MODEL_NAME": project.name,
            "REFERENCE_DATA_URL": self.storage.presigned_get(monitor.reference_uri, 7200),
            "HTML_S3_URI": uris["report.html"],
            "REPORT_JSON_S3_URI": uris["report.json"],
            "SUMMARY_JSON_S3_URI": uris["summary.json"],
            "HTML_UPLOAD_URL": self.storage.presigned_put(uris["report.html"], 7200, "text/html"),
            "REPORT_JSON_UPLOAD_URL": self.storage.presigned_put(uris["report.json"], 7200, "application/json"),
            "SUMMARY_JSON_UPLOAD_URL": self.storage.presigned_put(uris["summary.json"], 7200, "application/json"),
            "CONTROL_PLANE_WEBHOOK_URL": (
                f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/webhooks/drift-runs/{drift_run.public_id}/"
            ),
            "CONTROL_PLANE_INTERNAL_URL": settings.CONTROL_PLANE_INTERNAL_URL,
            "CONTROL_PLANE_WEBHOOK_SECRET": settings.CONTROL_PLANE_WEBHOOK_SECRET,
            "DRIFT_RUN_ID": str(drift_run.public_id),
            "REDIS_URL": settings.REDIS_URL,
            "DB_HOST_RO": os.environ.get("DB_HOST_RO", "postgres"),
            "DB_USER": os.environ.get("DB_USER", "postgres"),
            "DB_PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "DB_NAME": os.environ.get("DB_NAME", "mlops_paas_db"),
            "DB_PORT": os.environ.get("DB_PORT", "5432"),
            "DB_SCHEMA": settings.DB_SCHEMA,
        }
        from .job_containers import start

        drift_run.report_html_uri = uris["report.html"]
        drift_run.report_json_uri = uris["report.json"]
        drift_run.summary_uri = uris["summary.json"]
        rows = type(drift_run).objects.filter(pk=drift_run.pk)
        if drift_run.execution_check_token:
            from django.utils import timezone

            rows = rows.filter(
                execution_check_token=drift_run.execution_check_token, execution_check_lease_until__gt=timezone.now()
            )
        rows.update(
            report_html_uri=drift_run.report_html_uri,
            report_json_uri=drift_run.report_json_uri,
            summary_uri=drift_run.summary_uri,
        )
        container = start(
            self.docker,
            drift_run,
            "drift",
            image="mlops-paas-evidently",
            name=f"drift-{drift_run.public_id}",
            environment=environment,
            network=settings.DOCKER_NETWORK_NAME,
        )
        return {"dispatched": True, "container_id": container.id}

    def poll(self, drift_run):
        from .job_containers import observe

        return observe(self.docker.client, drift_run, "drift")

    def cleanup(self, drift_run):
        from .job_containers import remove

        return remove(self.docker.client, drift_run, "drift")

    def cancel(self, drift_run):
        return {"dispatched": False, **self.cleanup(drift_run)}
