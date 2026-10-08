import base64
import os

import docker
import docker.errors
from django.conf import settings

from apps.deployment.models import Endpoint
from apps.training.services.capabilities import issue_capability
from apps.training.services.storage_scope import validate_training_uri
from infrastructure.docker import DockerClient
from infrastructure.http import HttpClient
from infrastructure.runtime_health import healthy_payload
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import build_prefix, drift_run_prefix

from .build_inputs import label_mapping_input
from .image_references import build_image_tag, image_repository, immutable_image_reference
from .local_containers import remove_container, start_container


def _logging_environment():
    # Forward formatting and summary controls; each child logs at INFO.
    return {
        "LOG_FORMAT": os.environ.get("LOG_FORMAT") or "console",
        "LOG_SUMMARY_INTERVAL_SECONDS": os.environ.get("LOG_SUMMARY_INTERVAL_SECONDS") or "60",
    }


class DockerBuildBackend:
    def __init__(self, docker_client=None, storage=None):
        self.docker = docker_client or DockerClient()
        self.storage = storage or S3Storage()

    def run(self, build):
        project = build.project
        source = build.input_assets.filter(kind__in=("source_artifact", "training_output")).first()
        if source is None and build.version_id:
            source = (
                build.version.artifacts.filter(kind__in=("source", "training_output")).order_by("-created_at").first()
            )
        if not source:
            raise RuntimeError("The build has no source artifact.")
        source_uri = getattr(source, "s3_uri", "") or source.uri
        label_mapping_url, label_mapping_filename = label_mapping_input(build, self.storage)
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
            "LABEL_MAPPING_DOWNLOAD_URL": label_mapping_url,
            "LABEL_MAPPING_FILENAME": label_mapping_filename,
            "OUTPUT_UPLOAD_URL": self.storage.presigned_put(package_uri, 14400),
            "CONTROL_PLANE_WEBHOOK_URL": webhook,
            "CONTROL_PLANE_WEBHOOK_SECRET": settings.CONTROL_PLANE_WEBHOOK_SECRET,
            "HARBOR_REGISTRY_URL": settings.HARBOR_REGISTRY_URL,
            "HARBOR_USER_PROJECT": settings.HARBOR_USER_PROJECT,
            "HARBOR_USERNAME": settings.HARBOR_USERNAME,
            "HARBOR_PASSWORD": settings.HARBOR_PASSWORD,
            "REDIS_URL": settings.REDIS_URL,
        }
        container = start_container(
            self.docker,
            build,
            "build",
            image="mlops-paas-model-packager",
            name=f"build-{build.public_id}",
            environment=environment,
            network=settings.DOCKER_NETWORK_NAME,
            volumes={"/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"}},
        )
        return {"dispatched": True, "container_id": container.id}

    def cancel(self, build):
        remove_container(build, "build", self.docker.client)


class DockerTrainingBackend:
    def __init__(self, docker_client=None, storage=None):
        self.docker = docker_client or DockerClient(timeout=3)
        self.storage = storage or S3Storage()

    def run(self, job):
        project = job.project
        validate_training_uri(job, self.storage.bucket, "code", job.code_snapshot_uri)
        validate_training_uri(job, self.storage.bucket, "data", job.data_snapshot_uri)
        validate_training_uri(job, self.storage.bucket, "output", job.output_uri)
        output_upload_capability = issue_capability(job, "output_upload", preserve_existing=True)
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
            "S3_INPUT_DOWNLOAD_URL": f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/training-jobs/{job.public_id}/input-download-urls/",
            "S3_INPUT_DOWNLOAD_CAPABILITY": issue_capability(job, "input_download", preserve_existing=True),
            "MAX_RUNTIME_SECONDS": str(job.max_runtime_seconds),
            "ENTRY_POINT": job.entry_point,
            "MODEL_VERSION": "",
            "TRAINING_JOB_ID": str(job.public_id),
            "TENANT_ID": project.owner.tenant_id,
            "REQUIREMENTS_TEXT": base64.b64encode(job.requirements_text.encode()).decode()
            if job.requirements_text
            else "",
            "REDIS_URL": settings.REDIS_URL,
        }
        from .job_containers import start

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
            device_requests=[docker.types.DeviceRequest(count=job.accelerator_count, capabilities=[["gpu"]])] if job.accelerator_type == "gpu" else [],
        )
        return {"dispatched": True, "container_id": container.id}

    def poll(self, job):
        from .job_containers import observe

        return observe(self.docker.client, job, "training")

    def cleanup(self, job):
        from .job_containers import remove

        return remove(self.docker.client, job, "training")

    def cancel(self, job):
        return {"dispatched": False, **self.cleanup(job)}


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
        container_name = f"deploy-{deployment.public_id}"
        target_port = 5002 if deployment.version.flavor in {"pytorch", "tensorflow", "keras"} else 5001
        internal_url = f"http://{container_name}:{target_port}"
        public_path = f"/{project.owner.tenant_id}/models/{project.public_id}/{deployment.version.public_id}"
        public_url = f"{settings.MODEL_SERVER_PUBLIC_URL}{public_path}"
        labels = {
            "traefik.enable": "false",
            "mlops_project_id": str(project.public_id),
            "mlops_version_id": str(deployment.version.public_id),
            "mlops_deployment_id": str(deployment.public_id),
            "mlops_tenant_id": str(project.owner.tenant_id),
        }
        self._log(f"Creating runtime container {container_name}.")
        container = start_container(
            self.docker,
            deployment,
            "deploy",
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
        self._log("Runtime container created; readiness will be checked asynchronously.")
        return endpoint

    def stop(self, deployment):
        remove_container(deployment, "deploy", self.docker.client)

    def health(self, deployment):
        endpoint = getattr(deployment, "endpoint", None)
        if not endpoint:
            return False, {"status": "missing"}
        try:
            method = "POST" if deployment.version.flavor in {"pytorch", "tensorflow"} else "GET"
            response = self.http.request(method, f"{endpoint.internal_url}/health", **({"json": {}} if method == "POST" else {}))
            payload = response.json()
            healthy = healthy_payload(payload, project_id=deployment.version.project.public_id, version_id=deployment.version.public_id)
            return healthy, payload if isinstance(payload, dict) else {"status": "unhealthy"}
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
        source = monitor.version.artifacts.filter(kind__in=("source", "training_output")).first()
        environment = {
            **_logging_environment(),
            "JOB_ID": str(drift_run.public_id),
            "TENANT_ID": project.owner.tenant_id,
            "PROJECT_ID": str(project.public_id),
            "MODEL_VERSION_ID": str(monitor.version.public_id),
            "MODEL_NAME": project.name,
            "MODEL_URI": source.uri if source else "",
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
            rows = rows.filter(execution_check_token=drift_run.execution_check_token, execution_check_lease_until__gt=timezone.now())
        rows.update(report_html_uri=drift_run.report_html_uri, report_json_uri=drift_run.report_json_uri, summary_uri=drift_run.summary_uri)
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
