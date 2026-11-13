import docker.errors
from django.conf import settings

from infrastructure.docker import DockerClient
from infrastructure.harbor import HarborClient

from .image_references import image_repository, tagged_image_reference, version_image_tag


class DockerImageRegistry:
    def __init__(self, docker_client=None):
        self.docker = docker_client or DockerClient()

    def promote(self, *, build, version, image_uri, image_digest=""):
        repository = image_repository(build.project.public_id)
        tag = version_image_tag(version.version)
        final_reference = tagged_image_reference(repository, tag)
        # A retry after a failed registration phase finds the temporary tag already
        # removed, so fall back to the final tag instead of failing for good.
        candidates = [image_digest or image_uri, image_uri, final_reference]
        image = None
        for candidate in dict.fromkeys(candidates):
            try:
                image = self.docker.client.images.get(candidate)
                break
            except docker.errors.NotFound:
                continue
        if image is None:
            raise RuntimeError("Docker image to register no longer exists locally.")
        image.tag(repository, tag=tag)
        identity = image.attrs.get("Id") or image.id or image_digest
        if image_uri != final_reference:
            try:
                self.docker.client.images.remove(image_uri, force=False, noprune=False)
            except docker.errors.NotFound:
                pass
            except docker.errors.APIError:
                # The temporary tag is only cosmetic once the final tag exists.
                pass
        return final_reference, identity


class HarborImageRegistry:
    def __init__(self, harbor=None):
        self.harbor = harbor or HarborClient()

    def promote(self, *, build, version, image_uri, image_digest=""):
        if not image_digest:
            raise RuntimeError("Harbor image registration requires an OCI manifest digest.")
        tag = version_image_tag(version.version)
        self.harbor.create_tag(image_uri, tag, reference=image_digest)
        temporary_tag = image_uri.rsplit(":", 1)[-1]
        if temporary_tag != tag:
            try:
                self.harbor.delete_tag(image_uri, temporary_tag)
            except Exception:
                pass
        repository = image_repository(
            build.project.public_id,
            registry=settings.HARBOR_REGISTRY_URL,
            registry_project=settings.HARBOR_USER_PROJECT,
        )
        return tagged_image_reference(repository, tag), image_digest


def image_registry_for(build):
    return HarborImageRegistry() if build.backend == "argo" else DockerImageRegistry()
