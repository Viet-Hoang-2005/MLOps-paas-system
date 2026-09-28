from http.client import HTTPMessage
from types import SimpleNamespace

import requests
from requests.cookies import MockRequest, MockResponse

from infrastructure.execution.image_references import (
    immutable_image_reference,
    repository_from_reference,
    temporary_image_reference,
)
from infrastructure.execution.image_registry import DockerImageRegistry, HarborImageRegistry
from infrastructure.harbor import HarborClient


def test_image_reference_contract_is_project_scoped():
    project_id = "11111111-1111-1111-1111-111111111111"
    build_id = "22222222-2222-2222-2222-222222222222"

    assert temporary_image_reference(project_id, build_id) == (f"image-{project_id}:build-{build_id}")
    assert (
        temporary_image_reference(
            project_id,
            build_id,
            registry="https://registry.example/",
            registry_project="user-images",
        )
        == f"registry.example/user-images/image-{project_id}:build-{build_id}"
    )
    assert repository_from_reference("registry.example:5443/user-images/image-project:v1") == (
        "registry.example:5443/user-images/image-project"
    )


def test_immutable_reference_uses_local_image_id_or_harbor_digest():
    local = SimpleNamespace(backend="docker", image_uri="image-project:v1", image_digest="sha256:local")
    harbor = SimpleNamespace(
        backend="argo",
        image_uri="registry.example/user-images/image-project:v1",
        image_digest="sha256:manifest",
    )

    assert immutable_image_reference(local) == "sha256:local"
    assert immutable_image_reference(harbor) == ("registry.example/user-images/image-project@sha256:manifest")


def test_docker_promotion_adds_version_tag_and_removes_temporary_tag():
    image = SimpleNamespace(
        attrs={"Id": "sha256:local-image-id"},
        id="sha256:local-image-id",
        tag=lambda repository, tag: calls.append(("tag", repository, tag)),
    )
    calls = []
    images = SimpleNamespace(
        get=lambda reference: calls.append(("get", reference)) or image,
        remove=lambda reference, force, noprune: calls.append(("remove", reference, force, noprune)),
    )
    registry = DockerImageRegistry(docker_client=SimpleNamespace(client=SimpleNamespace(images=images)))
    project = SimpleNamespace(public_id="project-id")
    build = SimpleNamespace(project=project)
    version = SimpleNamespace(version="3")

    uri, identity = registry.promote(
        build=build,
        version=version,
        image_uri="image-project-id:build-build-id",
    )

    assert (uri, identity) == ("image-project-id:v3", "sha256:local-image-id")
    assert calls == [
        ("get", "image-project-id:build-build-id"),
        ("tag", "image-project-id", "v3"),
        ("remove", "image-project-id:build-build-id", False, False),
    ]


def test_harbor_promotion_retags_digest_and_removes_temporary_tag(settings):
    settings.HARBOR_REGISTRY_URL = "registry.example"
    settings.HARBOR_USER_PROJECT = "user-images"
    calls = []
    harbor = SimpleNamespace(
        create_tag=lambda uri, tag, reference: calls.append(("create", uri, tag, reference)),
        delete_tag=lambda uri, tag: calls.append(("delete", uri, tag)),
    )
    registry = HarborImageRegistry(harbor=harbor)
    build = SimpleNamespace(project=SimpleNamespace(public_id="project-id"))
    version = SimpleNamespace(version="4")
    temporary_uri = "registry.example/user-images/image-project-id:build-build-id"

    uri, identity = registry.promote(
        build=build,
        version=version,
        image_uri=temporary_uri,
        image_digest="sha256:manifest",
    )

    assert (uri, identity) == (
        "registry.example/user-images/image-project-id:v4",
        "sha256:manifest",
    )
    assert calls == [
        ("create", temporary_uri, "v4", "sha256:manifest"),
        ("delete", temporary_uri, "build-build-id"),
    ]


def test_harbor_client_creates_version_tag_then_deletes_only_build_tag(settings):
    settings.HARBOR_REGISTRY_URL = "registry.example"
    settings.HARBOR_USERNAME = "robot"
    settings.HARBOR_PASSWORD = "secret"
    calls = []
    http = SimpleNamespace(request=lambda method, url, **kwargs: calls.append((method, url, kwargs)))
    harbor = HarborClient(http=http)
    uri = "registry.example/user-images/image-project-id:build-build-id"

    assert harbor.create_tag(uri, "v1", reference="sha256:manifest") == "created"
    assert harbor.delete_tag(uri, "build-build-id") == "deleted"

    assert calls[0][0] == "POST"
    assert "/artifacts/sha256%3Amanifest/tags" in calls[0][1]
    assert calls[0][2]["json"] == {"name": "v1"}
    assert calls[1][0] == "DELETE"
    assert calls[1][1].endswith("/artifacts/build-build-id/tags/build-build-id")


def test_harbor_client_session_never_replays_cookies(settings):
    settings.HARBOR_REGISTRY_URL = "registry.example"
    session = HarborClient().http.session
    headers = HTTPMessage()
    headers["Set-Cookie"] = "sid=abc; Path=/"
    request = requests.Request("GET", "https://registry.example/api/v2.0/projects").prepare()

    session.cookies.extract_cookies(MockResponse(headers), MockRequest(request))

    assert len(session.cookies) == 0


def _harbor_http(responses):
    """Answer each (method, path after /artifacts) with queued outcomes; ints raise HTTPError."""
    calls = []

    def request(method, url, **kwargs):
        path = url.rsplit("/artifacts", 1)[-1]
        calls.append((method, path))
        queued = responses.get((method, path), [])
        outcome = queued.pop(0) if queued else None
        if isinstance(outcome, int):
            raise requests.HTTPError(response=SimpleNamespace(status_code=outcome))
        return SimpleNamespace(json=lambda: outcome or {})

    return SimpleNamespace(request=request), calls


def test_harbor_client_keeps_tag_already_on_expected_digest(settings):
    settings.HARBOR_REGISTRY_URL = "registry.example"
    http, calls = _harbor_http({("POST", "/sha256%3Anew/tags"): [409], ("GET", "/v1"): [{"digest": "sha256:new"}]})
    uri = "registry.example/user-images/image-project-id:build-build-id"

    assert HarborClient(http=http).create_tag(uri, "v1", reference="sha256:new") == "already-exists"
    assert calls == [("POST", "/sha256%3Anew/tags"), ("GET", "/v1")]


def test_harbor_client_moves_tag_left_on_orphaned_artifact(settings):
    settings.HARBOR_REGISTRY_URL = "registry.example"
    http, calls = _harbor_http({("POST", "/sha256%3Anew/tags"): [409], ("GET", "/v1"): [{"digest": "sha256:old"}]})
    uri = "registry.example/user-images/image-project-id:build-build-id"

    assert HarborClient(http=http).create_tag(uri, "v1", reference="sha256:new") == "moved"
    assert calls == [
        ("POST", "/sha256%3Anew/tags"),
        ("GET", "/v1"),
        ("DELETE", "/v1/tags/v1"),
        ("POST", "/sha256%3Anew/tags"),
    ]
