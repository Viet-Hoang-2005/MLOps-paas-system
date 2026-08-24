from urllib.parse import quote

from django.conf import settings
from requests import HTTPError

from infrastructure.http import HttpClient


class HarborClient:
    def __init__(self, http=None):
        self.http = http or HttpClient()
        registry = settings.HARBOR_REGISTRY_URL
        self.base_url = (
            registry if registry.startswith(("http://", "https://")) else f"https://{registry}"
        ) if registry else ""

    @property
    def enabled(self):
        return bool(self.base_url)

    def delete_repository(self, project, repository):
        if not self.enabled:
            return
        encoded = quote(repository, safe="")
        url = f"{self.base_url}/api/v2.0/projects/{project}/repositories/{encoded}"
        try:
            self.http.request("DELETE", url, auth=(settings.HARBOR_USERNAME, settings.HARBOR_PASSWORD))
        except HTTPError as exc:
            if getattr(exc.response, "status_code", None) == 404:
                return "already-absent"
            raise
        return "deleted"

    def create_tag(self, image_uri, tag, *, reference=""):
        """Create an idempotent human tag for an existing Harbor artifact."""
        if not self.enabled:
            raise RuntimeError("Harbor image registration requires HARBOR_REGISTRY_URL.")
        project, repository, current_reference = self._parse_image_uri(image_uri)
        reference = reference or current_reference
        url = (
            f"{self.base_url}/api/v2.0/projects/{quote(project, safe='')}/repositories/"
            f"{quote(repository, safe='')}/artifacts/{quote(reference, safe='')}/tags"
        )
        try:
            self.http.request(
                "POST",
                url,
                json={"name": tag},
                auth=(settings.HARBOR_USERNAME, settings.HARBOR_PASSWORD),
            )
        except HTTPError as exc:
            if getattr(exc.response, "status_code", None) == 409:
                return "already-exists"
            raise
        return "created"

    def delete_tag(self, image_uri, tag):
        """Remove one tag while preserving the manifest and its version tag."""
        if not self.enabled:
            raise RuntimeError("Harbor tag cleanup requires HARBOR_REGISTRY_URL.")
        project, repository, reference = self._parse_image_uri(image_uri)
        url = (
            f"{self.base_url}/api/v2.0/projects/{quote(project, safe='')}/repositories/"
            f"{quote(repository, safe='')}/artifacts/{quote(reference, safe='')}/tags/{quote(tag, safe='')}"
        )
        try:
            self.http.request("DELETE", url, auth=(settings.HARBOR_USERNAME, settings.HARBOR_PASSWORD))
        except HTTPError as exc:
            if getattr(exc.response, "status_code", None) == 404:
                return "already-absent"
            raise
        return "deleted"

    def _parse_image_uri(self, image_uri):
        image = str(image_uri).replace("https://", "").replace("http://", "").strip("/")
        parts = image.split("/")
        if len(parts) < 3:
            raise ValueError("A Harbor image URI must include registry, project, repository, and tag.")
        registry, project, *repository_parts = parts
        configured_registry = self.base_url.split("://", 1)[-1].strip("/")
        if registry != configured_registry:
            raise ValueError("Image registry does not match the configured Harbor registry.")
        image_name = repository_parts[-1]
        if "@" in image_name:
            repository_name, reference = image_name.split("@", 1)
        elif ":" in image_name:
            repository_name, reference = image_name.rsplit(":", 1)
        else:
            raise ValueError("A Harbor image URI must include a tag or digest.")
        repository = "/".join([*repository_parts[:-1], repository_name])
        return project, repository, reference

    def delete_artifact(self, image_uri):
        """Delete one tagged Harbor artifact, never an entire tenant repository."""
        if not self.enabled:
            raise RuntimeError("Harbor image cleanup requires HARBOR_REGISTRY_URL.")

        project, repository, reference = self._parse_image_uri(image_uri)
        url = (
            f"{self.base_url}/api/v2.0/projects/{quote(project, safe='')}/repositories/"
            f"{quote(repository, safe='')}/artifacts/{quote(reference, safe='')}"
        )
        try:
            self.http.request("DELETE", url, auth=(settings.HARBOR_USERNAME, settings.HARBOR_PASSWORD))
        except HTTPError as exc:
            if getattr(exc.response, "status_code", None) == 404:
                return "already-absent"
            raise
        return "deleted"

    def repositories(self, project):
        if not self.enabled:
            return []
        repositories: list[str] = []
        page = 1
        while True:
            response = self.http.request(
                "GET",
                f"{self.base_url}/api/v2.0/projects/{project}/repositories",
                params={"page": page, "page_size": 100},
                auth=(settings.HARBOR_USERNAME, settings.HARBOR_PASSWORD),
            )
            batch = response.json()
            prefix = f"{project}/"
            repositories.extend(
                item["name"][len(prefix) :] if item["name"].startswith(prefix) else item["name"]
                for item in batch
            )
            if len(batch) < 100:
                return repositories
            page += 1
