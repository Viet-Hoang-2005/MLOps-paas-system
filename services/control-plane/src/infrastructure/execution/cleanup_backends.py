import docker
import docker.errors
from django.conf import settings

from infrastructure.argo import ArgoWebhookClient
from infrastructure.docker import DockerClient
from infrastructure.harbor import HarborClient

from .image_references import image_repository, local_image_repository


class DockerProjectCleanupBackend:
    def __init__(self, docker_client=None):
        self.docker = docker_client or DockerClient()

    def run(self, project, manifest):
        client = self.docker.client
        removed = {"containers": [], "images": []}
        for name in manifest["container_names"]:
            _validate_container_name(name)
            try:
                client.containers.get(name).remove(force=True)
                removed["containers"].append(name)
            except docker.errors.NotFound:
                pass
        for image_uri in manifest["image_uris"]:
            _validate_project_image(project, image_uri)
            try:
                client.images.remove(image=image_uri, force=True, noprune=False)
                removed["images"].append(image_uri)
            except docker.errors.ImageNotFound:
                pass
        return {"dispatched": False, "removed": removed}

    def delete_images(self, project, manifest):
        return []


class ArgoProjectCleanupBackend:
    def __init__(self, client=None, harbor_client=None):
        self.client = client or ArgoWebhookClient()
        self.harbor = harbor_client or HarborClient()

    def run(self, project, manifest):
        response = self.client.trigger(
            settings.ARGO_DELETE_WEBHOOK_URL,
            {
                "project_id": str(project.public_id),
                "container_names": manifest["container_names"],
                "control_plane_webhook_url": (
                    f"{settings.CONTROL_PLANE_INTERNAL_URL}/internal/webhooks/project-deletions/{project.public_id}/"
                ),
            },
        )
        return {"dispatched": True, "response": response}

    def delete_images(self, project, manifest):
        repository = local_image_repository(project.public_id)
        return [self.harbor.delete_repository(settings.HARBOR_USER_PROJECT, repository)]


def project_cleanup_backend():
    return ArgoProjectCleanupBackend() if settings.EXECUTION_BACKEND == "argo" else DockerProjectCleanupBackend()


def _validate_container_name(name):
    if not str(name).startswith("deploy-") or any(char.isspace() for char in str(name)):
        raise ValueError("Project cleanup can only remove deployment containers named deploy-<BUILD_ID>.")


def _validate_project_image(project, image_uri):
    image_name = str(image_uri).replace("https://", "").replace("http://", "").strip("/").rsplit("/", 1)[-1]
    repository_name = image_name.split("@", 1)[0].split(":", 1)[0]
    expected = image_repository(project.public_id)
    if repository_name != expected:
        raise ValueError("Project cleanup can only remove images from its canonical project repository.")
