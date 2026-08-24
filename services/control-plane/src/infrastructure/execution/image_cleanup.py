"""Infrastructure adapter for removing a build image from its execution registry."""

import docker

from infrastructure.docker import DockerClient
from infrastructure.harbor import HarborClient


class BuildImageCleaner:
    """Delete only an image named by a concrete Build record.

    Docker builds are local Docker Desktop images. Argo builds are published to
    Harbor and must be removed through Harbor's artifact API instead of a pod
    Docker socket.
    """

    def __init__(self, docker_client=None, harbor_client=None):
        self.docker = docker_client
        self.harbor = harbor_client

    def delete(self, build):
        if not build.image_uri:
            return "no-image-reference"
        if build.backend == "argo":
            harbor = self.harbor or HarborClient()
            return harbor.delete_artifact(build.image_uri)
        docker_client = self.docker or DockerClient()
        try:
            docker_client.client.images.remove(build.image_uri, force=True, noprune=False)
        except docker.errors.NotFound:
            return "already-absent"
        return "deleted"
