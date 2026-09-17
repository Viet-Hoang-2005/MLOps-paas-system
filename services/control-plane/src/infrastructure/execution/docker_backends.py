import base64
import os
import time

import docker
import docker.errors
from apps.deployment.models import Endpoint
from apps.training.services.capabilities import issue_capability
from apps.training.services.storage_scope import validate_training_uri
from django.conf import settings
from django.utils import timezone

from infrastructure.docker import DockerClient
from infrastructure.http import HttpClient
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import build_prefix, drift_run_prefix

from .image_references import build_image_tag, image_repository, immutable_image_reference


def _logging_environment():
    # Forward formatting and summary controls; each child logs at INFO.
    return {
        "LOG_FORMAT": os.environ.get("LOG_FORMAT") or "console",
        "LOG_SUMMARY_INTERVAL_SECONDS": os.environ.get("LOG_SUMMARY_INTERVAL_SECONDS") or "60",
    }


def _wait_and_cleanup(container):
    result = container.wait()
    logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
    if result.get("StatusCode") == 0:
        try:
            container.remove()
        except docker.errors.NotFound:
            pass
    return result.get("StatusCode", 1), logs


class DockerBuildBackend:
    def __init__(self, docker_client=None, storage=None):
        self.docker = docker_client or DockerClient()
        self.storage = storage or S3Storage()

    def run(self, build):
        project = build.project
        source = build.input_assets.filter(kind__in=("source_artifact", "training_output")).first()
        if source is None and build.version_id:
            source = (
                build.version.artifacts.filter(kind__in=("source", "training_output"))
                .order_by("-created_at")
                .first()
            )
        if not source:
            raise RuntimeError("The build has no source artifact.")
        source_uri = getattr(source, "s3_uri", "") or source.uri
        package_root = build_prefix(project.owner.tenant_id, project.public_id, build.public_id)
        package_uri = f"s3://{self.storage.bucket}/{package_root}/artifacts/model-package.zip"
        build.package_uri = package_uri
        build.save(update_fields=["package_uri", "updated_at"])
        webhook = f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/webhooks/builds/{build.public_id}/"
        task_type = "TEST_ZIP" if build.artifact_format == "mlflow_zip" else "BUILD"
        environment = {
            **_logging_environment(),
            "TASK_TYPE": task_type,
            "BUILD_ID": str(build.public_id),
            "PROJECT_ID": str(project.public_id),
            "TENANT_ID": project.owner.tenant_id,
            "IMAGE_REPOSITORY": image_repository(project.public_id),
            "IMAGE_TAG": build_image_tag(build.public_id),
            "FLAVOR": build.flavor,
            "REQUIREMENTS_TEXT": build.requirements_snapshot,
            "SOURCE_ARTIFACT_NAME": source.name,
            "SOURCE_TYPE": "training_job" if build.source_job_id else "manual_upload",
            "SOURCE_DOWNLOAD_URL": self.storage.presigned_get(source_uri, 14400),
            "OUTPUT_UPLOAD_URL": self.storage.presigned_put(package_uri, 14400),
            "CONTROL_PLANE_WEBHOOK_URL": webhook,
            "CONTROL_PLANE_WEBHOOK_SECRET": settings.CONTROL_PLANE_WEBHOOK_SECRET,
            "HARBOR_REGISTRY_URL": settings.HARBOR_REGISTRY_URL,
            "HARBOR_USER_PROJECT": settings.HARBOR_USER_PROJECT,
            "HARBOR_USERNAME": settings.HARBOR_USERNAME,
            "HARBOR_PASSWORD": settings.HARBOR_PASSWORD,
            "REDIS_URL": settings.REDIS_URL,
        }
        container = self.docker.run(
            image="mlops-paas-model-packager",
            name=f"build-{build.public_id}",
            environment=environment,
            network=settings.DOCKER_NETWORK_NAME,
            volumes={"/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"}},
        )
        build.external_build_id = container.id
        build.save(update_fields=["external_build_id", "updated_at"])
        status_code, logs = _wait_and_cleanup(container)
        if status_code:
            raise RuntimeError(logs[-12000:])
        return logs

    def cancel(self, build):
        if build.external_build_id:
            try:
                self.docker.client.containers.get(build.external_build_id).kill()
            except docker.errors.NotFound:
                pass


class DockerTrainingBackend:
    def __init__(self, docker_client=None, storage=None):
        self.docker = docker_client or DockerClient()
        self.storage = storage or S3Storage()

    def run(self, job):
        project = job.project
        validate_training_uri(job, self.storage.bucket, "code", job.code_snapshot_uri)
        validate_training_uri(job, self.storage.bucket, "data", job.data_snapshot_uri)
        validate_training_uri(job, self.storage.bucket, "output", job.output_uri)
        output_upload_capability = issue_capability(job, "output_upload")
        environment = {
            **_logging_environment(),
            "S3_SOURCE_URI": self.storage.presigned_get(
                job.code_snapshot_uri, settings.TRAINING_PRESIGNED_URL_TTL_SECONDS
            ),
            "S3_TRAINING_DATA_URI": self.storage.presigned_get(
                job.data_snapshot_uri, settings.TRAINING_PRESIGNED_URL_TTL_SECONDS
            ),
            "S3_OUTPUT_UPLOAD_URL": (
                f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/training-jobs/{job.public_id}/output-upload-url/"
            ),
            "S3_OUTPUT_UPLOAD_CAPABILITY": output_upload_capability,
            "ENTRY_POINT": job.entry_point,
            "MODEL_VERSION": "",
            "TRAINING_JOB_ID": str(job.public_id),
            "TENANT_ID": project.owner.tenant_id,
            "REQUIREMENTS_TEXT": base64.b64encode(job.requirements_text.encode()).decode()
            if job.requirements_text
            else "",
            "REDIS_URL": settings.REDIS_URL,
        }
        container = self.docker.run(
            image="mlops-paas-training-runner:latest",
            name=f"training-{job.public_id}",
            environment=environment,
            network=settings.DOCKER_NETWORK_NAME,
        )
        job.external_job_id = container.id
        job.save(update_fields=["external_job_id", "updated_at"])
        return {"dispatched": True, "container_id": container.id}

    def poll(self, job):
        if not job.external_job_id:
            return {"status": "failed", "error": "No container ID registered."}
        try:
            container = self.docker.client.containers.get(job.external_job_id)
            container.reload()
            state = container.attrs.get("State", {})
            status = state.get("Status", "").lower()
            if status in {"running", "created", "restarting"}:
                return {"status": "running"}
            exit_code = state.get("ExitCode", 0)
            logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
            try:
                container.remove(force=True)
            except docker.errors.NotFound:
                pass
            if exit_code == 0:
                return {"status": "completed", "logs": logs, "exit_code": 0}
            return {
                "status": "failed",
                "error": logs[-12000:],
                "logs": logs,
                "exit_code": exit_code,
            }
        except docker.errors.NotFound:
            return {"status": "not_found"}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def cancel(self, job):
        if getattr(job, "started_at", None) and not job.external_job_id:
            return {
                "dispatched": False,
                "confirmed": False,
                "retry": True,
                "detail": "Training execution started but the runtime container is not registered yet.",
            }
        if job.external_job_id:
            try:
                container = self.docker.client.containers.get(job.external_job_id)
                try:
                    container.kill()
                except docker.errors.APIError:
                    container.reload()
                    if container.status not in {"exited", "dead"}:
                        raise
                container.wait(timeout=30)
                try:
                    container.remove(force=True)
                except docker.errors.NotFound:
                    pass
            except docker.errors.NotFound:
                pass
        return {"dispatched": False, "confirmed": True}


class DockerDeploymentBackend:
    def __init__(self, docker_client=None, http=None, log_sink=None):
        self.docker = docker_client or DockerClient()
        self.http = http or HttpClient(timeout=(3.05, 10))
        self.log_sink = log_sink

    def _log(self, message):
        if self.log_sink:
            self.log_sink(message)

    def deploy(self, deployment):
        project = deployment.version.project
        image = immutable_image_reference(deployment.build)
        container_name = f"deploy-{deployment.build.public_id}"
        target_port = 5002 if deployment.version.flavor in {"pytorch", "tensorflow"} else 5001
        internal_url = f"http://{container_name}:{target_port}"
        public_path = f"/{project.owner.tenant_id}/models/{project.public_id}/{deployment.version.public_id}"
        public_url = f"{settings.MODEL_SERVER_PUBLIC_URL}{public_path}"
        labels = {"traefik.enable": "false"}
        self._log(f"Creating runtime container {container_name}.")
        container = self.docker.run(
            image=image,
            name=container_name,
            environment={
                **_logging_environment(),
                "PROJECT_ID": str(project.public_id),
                "MODEL_VERSION_ID": str(deployment.version.public_id),
                "MODEL_VERSION": deployment.version.version,
                "MODEL_URI": "/app/model_artifact",
                "TENANT_ID": project.owner.tenant_id,
            },
            labels=labels,
            network=settings.DOCKER_NETWORK_NAME,
            restart_policy={"Name": "always"},
        )
        deployment.external_deployment_id = container.id
        deployment.save(update_fields=["external_deployment_id", "updated_at"])
        endpoint, _ = Endpoint.objects.update_or_create(
            deployment=deployment,
            defaults={
                "public_url": public_url,
                "internal_url": internal_url,
                "runtime_name": container_name,
                "health_status": "unknown",
            },
        )
        self._log("Runtime container created; waiting for model worker health endpoint.")
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            healthy, metadata = self.health(deployment)
            if healthy:
                self._log("Model worker health endpoint responded successfully.")
                endpoint.health_status = "healthy"
                endpoint.last_checked_at = timezone.now()
                endpoint.save(update_fields=["health_status", "last_checked_at", "updated_at"])
                return endpoint
            detail = metadata.get("message") or metadata.get("error") or metadata.get("detail")
            suffix = f" Reason: {detail}" if detail else ""
            self._log(f"Model worker is not healthy yet.{suffix} Checking again in 5 seconds.")
            time.sleep(5)
        try:
            container.remove(force=True)
        except docker.errors.DockerException as exc:
            self._log(f"Unable to remove the unhealthy runtime container: {exc}")
        raise RuntimeError("Endpoint did not become healthy before timeout.")

    def stop(self, deployment):
        if deployment.external_deployment_id:
            try:
                self.docker.client.containers.get(deployment.external_deployment_id).remove(force=True)
            except docker.errors.NotFound:
                pass

    def health(self, deployment):
        endpoint = getattr(deployment, "endpoint", None)
        if not endpoint:
            return False, {"status": "missing"}
        try:
            response = self.http.request("GET", f"{endpoint.internal_url}/health")
            payload = response.json()
            healthy = payload.get("model_loaded", payload.get("status") == "healthy")
            return bool(healthy and payload.get("status") != "unhealthy"), payload
        except Exception as exc:
            return False, {"status": "unhealthy", "detail": str(exc)}

    def logs(self, deployment):
        if not deployment.external_deployment_id:
            return ""
        try:
            container = self.docker.client.containers.get(deployment.external_deployment_id)
            return container.logs(stdout=True, stderr=True, tail=2000).decode("utf-8", errors="replace")
        except docker.errors.NotFound:
            return ""


class DockerDriftBackend:
    def __init__(self, docker_client=None, storage=None):
        self.docker = docker_client or DockerClient()
        self.storage = storage or S3Storage()

    def run(self, drift_run):
        monitor = drift_run.monitor
        project = monitor.version.project
        prefix = drift_run_prefix(project.owner.tenant_id, project.public_id, monitor.public_id, drift_run.public_id)
        uris = {
            name: f"s3://{self.storage.bucket}/{prefix}{name}"
            for name in ("report.html", "report.json", "summary.json")
        }
        source = monitor.version.artifacts.filter(kind__in=("source", "training_output")).first()
        environment = {
            **_logging_environment(),
            "JOB_ID": str(drift_run.public_id),
            "TENANT_ID": project.owner.tenant_id,
            "PROJECT_ID": str(project.public_id),
            "MODEL_VERSION_ID": str(monitor.version.public_id),
            "MODEL_NAME": project.name,
            "MODEL_URI": source.uri if source else "",
            "REFERENCE_DATA_URL": self.storage.presigned_get(monitor.reference_asset.s3_uri, 7200),
            "HTML_S3_URI": uris["report.html"],
            "REPORT_JSON_S3_URI": uris["report.json"],
            "SUMMARY_JSON_S3_URI": uris["summary.json"],
            "HTML_UPLOAD_URL": self.storage.presigned_put(uris["report.html"], 7200, "text/html"),
            "REPORT_JSON_UPLOAD_URL": self.storage.presigned_put(uris["report.json"], 7200, "application/json"),
            "SUMMARY_JSON_UPLOAD_URL": self.storage.presigned_put(uris["summary.json"], 7200, "application/json"),
            "CONTROL_PLANE_WEBHOOK_URL": (
                f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/webhooks/" f"drift-runs/{drift_run.public_id}/"
            ),
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
        container = self.docker.run(
            image="mlops-paas-evidently",
            name=f"drift-{drift_run.public_id}",
            environment=environment,
            network=settings.DOCKER_NETWORK_NAME,
        )
        drift_run.external_run_id = container.id
        drift_run.report_html_uri = uris["report.html"]
        drift_run.report_json_uri = uris["report.json"]
        drift_run.summary_uri = uris["summary.json"]
        drift_run.save(update_fields=["external_run_id", "report_html_uri", "report_json_uri", "summary_uri"])
        return {"dispatched": True, "container_id": container.id}

    def poll(self, drift_run):
        if not drift_run.external_run_id:
            return {"status": "failed", "error": "No container ID registered."}
        try:
            container = self.docker.client.containers.get(drift_run.external_run_id)
            container.reload()
            state = container.attrs.get("State", {})
            status = state.get("Status", "").lower()
            if status in {"running", "created", "restarting"}:
                return {"status": "running"}
            exit_code = state.get("ExitCode", 0)
            logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
            try:
                container.remove(force=True)
            except docker.errors.NotFound:
                pass
            if exit_code == 0:
                return {"status": "completed", "logs": logs, "exit_code": 0}
            return {
                "status": "failed",
                "error": logs[-12000:],
                "logs": logs,
                "exit_code": exit_code,
            }
        except docker.errors.NotFound:
            return {"status": "not_found"}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def cancel(self, drift_run):
        if drift_run.external_run_id:
            try:
                container = self.docker.client.containers.get(drift_run.external_run_id)
                try:
                    container.kill()
                except Exception:
                    pass
                container.remove(force=True)
            except docker.errors.NotFound:
                pass
        return {"dispatched": False, "confirmed": True}
