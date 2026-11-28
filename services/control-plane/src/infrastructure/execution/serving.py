import docker
import docker.errors
from django.conf import settings

from apps.deployment.models import Endpoint
from apps.deployment.serving.callback_tokens import issue_callback_token
from infrastructure.execution.argo_backend import _ArgoBackend
from infrastructure.execution.docker_client import DockerClient
from infrastructure.execution.docker_environment import _logging_environment
from infrastructure.execution.local_containers import remove_container, start_container
from infrastructure.http import HttpClient
from infrastructure.images.references import immutable_image_reference
from infrastructure.telemetry.runtime_health import healthy_payload, is_dl_flavor


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
        container_name = f"deploy-{str(deployment.public_id).lower()}"
        model_type = "dl" if is_dl_flavor(version.flavor) else "ml"
        target_port = 5002 if model_type == "dl" else 5001
        public_url = (
            f"{settings.MODEL_SERVER_PUBLIC_URL}/{project.owner.tenant_id}/models/"
            f"{project.public_id}/{version.public_id}"
        )
        endpoint = Endpoint.objects.update_or_create(
            deployment=deployment,
            defaults={
                "public_url": public_url,
                "internal_url": (
                    f"http://{container_name}-svc.{settings.MODEL_RUNTIME_NAMESPACE}.svc.cluster.local:{target_port}"
                ),
                "runtime_name": container_name,
                "runtime_namespace": settings.MODEL_RUNTIME_NAMESPACE,
                "health_status": "unknown",
            },
        )[0]
        self._log(f"Submitting Argo deployment workflow for runtime {container_name}.")
        self.trigger(
            {
                "deployment_id": str(deployment.public_id),
                "tenant_id": project.owner.tenant_id,
                "project_id": str(project.public_id),
                "model_version_id": str(version.public_id),
                "version": version.version,
                "image_name": immutable_image_reference(deployment.build),
                "container_name": container_name,
                "model_type": model_type,
                "target_port": str(target_port),
                "control_plane_webhook_url": (
                    f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/webhooks/deployments/{deployment.public_id}/"
                ),
                "callback_token": issue_callback_token(deployment.public_id),
                "model_uri": "/app/model_artifact",
            }
        )
        self._log("Argo workflow submitted; waiting for its readiness result callback.")
        return endpoint

    def stop(self, deployment):
        return self.request_runtime_stop(deployment, "deployment")

    def health(self, deployment):
        endpoint = getattr(deployment, "endpoint", None)
        if not endpoint or not endpoint.internal_url:
            return False, {"status": "missing"}
        try:
            method = "POST" if is_dl_flavor(deployment.version.flavor) else "GET"
            response = self.http.request(
                method, f"{endpoint.internal_url}/health", **({"json": {}} if method == "POST" else {})
            )
            payload = response.json()
            healthy = healthy_payload(
                payload, project_id=deployment.version.project.public_id, version_id=deployment.version.public_id
            )
            return healthy, payload if isinstance(payload, dict) else {"status": "unhealthy"}
        except Exception as exc:
            return False, {"status": "unhealthy", "detail": str(exc)}

    def logs(self, deployment):
        endpoint = getattr(deployment, "endpoint", None)
        return str(endpoint.metadata.get("logs", "")) if endpoint else ""
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
        target_port = 5002 if is_dl_flavor(deployment.version.flavor) else 5001
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
            method = "POST" if is_dl_flavor(deployment.version.flavor) else "GET"
            response = self.http.request(
                method, f"{endpoint.internal_url}/health", **({"json": {}} if method == "POST" else {})
            )
            payload = response.json()
            healthy = healthy_payload(
                payload, project_id=deployment.version.project.public_id, version_id=deployment.version.public_id
            )
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
