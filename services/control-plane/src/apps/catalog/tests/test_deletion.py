from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from infrastructure.execution.cleanup_backends import DockerProjectCleanupBackend
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.catalog.services.deletion import finalize_project_deletion, project_cleanup_manifest
from apps.deployment.models import Build, Deployment, Endpoint
from apps.registry.models import ModelVersion


class FakeStorage:
    def __init__(self):
        self.prefixes = []

    def delete_prefix(self, prefix):
        self.prefixes.append(prefix)


@pytest.mark.django_db
def test_delete_endpoint_marks_the_entire_project_deleting_and_enqueues_cleanup(
    django_capture_on_commit_callbacks, monkeypatch
):
    owner = get_user_model().objects.create_user("delete-owner@example.com", "password123") # type: ignore[attr-defined]
    project = ModelProject.objects.create(owner=owner, name="Delete me")
    queued = []
    monkeypatch.setattr(
        "apps.catalog.tasks.execute_project_deletion.delay",
        lambda project_id: queued.append(project_id) or SimpleNamespace(id="cleanup-task"),
    )
    client = APIClient()
    client.force_authenticate(owner)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.delete(f"/api/models/{project.public_id}/")

    project.refresh_from_db()
    assert response.status_code == 202
    assert project.is_active is False
    assert project.deletion_state == "deleting"
    assert project.deletion_task_id == "cleanup-task"
    assert queued == [str(project.public_id)]


@pytest.mark.django_db
def test_cleanup_manifest_includes_all_project_build_images_and_runtime_names():
    owner = get_user_model().objects.create_user("manifest-owner@example.com", "password123") # type: ignore[attr-defined]
    project = ModelProject.objects.create(owner=owner, name="All image history")
    first = ModelVersion.objects.create(project=project, version="1")
    second = ModelVersion.objects.create(project=project, version="2")
    repository = f"image-{project.public_id}"
    old_build = Build.objects.create(
        project=project, version=first, flavor="sklearn", status="ready", image_uri=f"{repository}:v1"
    )
    new_build = Build.objects.create(
        project=project, version=second, flavor="sklearn", status="ready", image_uri=f"{repository}:v2"
    )
    deployment = Deployment.objects.create(version=first, build=old_build, status="stopped")
    Endpoint.objects.create(deployment=deployment, public_url="http://example.test", runtime_name="deploy-old")

    manifest = project_cleanup_manifest(project)

    assert manifest["image_uris"] == sorted([
        f"{repository}:v1",
        f"{repository}:v2",
        f"{repository}:build-{old_build.public_id}",
        f"{repository}:build-{new_build.public_id}",
    ])
    # A stopped deployment is still included: project deletion must clean stale runtimes too.
    assert manifest["container_names"] == ["deploy-old"]
    assert new_build.public_id


@pytest.mark.django_db
def test_finalization_deletes_project_s3_prefix_and_archives_database_rows():
    owner = get_user_model().objects.create_user("finalize-owner@example.com", "password123") # type: ignore[attr-defined]
    project = ModelProject.objects.create(owner=owner, name="Finalize me", deletion_state="deleting", is_active=False)
    version = ModelVersion.objects.create(project=project, version="1")
    build = Build.objects.create(
        project=project,
        version=version,
        flavor="sklearn",
        status="ready",
        image_uri=f"image-{project.public_id}:v1",
    )
    deployment = Deployment.objects.create(version=version, build=build, status="healthy")
    endpoint = Endpoint.objects.create(
        deployment=deployment,
        public_url="http://example.test",
        runtime_name="deploy-finalize",
    )
    storage = FakeStorage()

    result = finalize_project_deletion(project, storage=storage)
    deployment.refresh_from_db()
    endpoint.refresh_from_db()

    assert result.deletion_state == "deleted"
    assert result.deleted_at is not None
    assert storage.prefixes == [f"users/{owner.tenant_id}/models/{project.public_id}"]
    assert deployment.status == "stopped"
    assert endpoint.health_status == "stopped"
    assert ModelVersion.objects.filter(pk=version.pk).exists()  # audit/history is retained.


def test_local_cleanup_uses_docker_sdk_without_a_model_cleaner_container():
    removed = []

    class Containers:
        def get(self, name):
            return SimpleNamespace(remove=lambda force: removed.append(("container", name, force)))

    class Images:
        def remove(self, image, force, noprune):
            removed.append(("image", image, force, noprune)) # type: ignore[attr-defined]

    client = SimpleNamespace(containers=Containers(), images=Images())
    backend = DockerProjectCleanupBackend(docker_client=SimpleNamespace(client=client))

    project = SimpleNamespace(public_id="11111111-1111-1111-1111-111111111111")
    image_uri = f"image-{project.public_id}:v1"
    result = backend.run(
        project,
        {"container_names": ["deploy-build-1"], "image_uris": [image_uri]},
    )

    assert result["dispatched"] is False
    assert removed == [
        ("container", "deploy-build-1", True),
        ("image", image_uri, True, False),
    ]
