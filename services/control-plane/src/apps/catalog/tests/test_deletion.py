from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.catalog.services.deletion import finalize_project_deletion, project_cleanup_manifest
from apps.deployment.models import Build, Deployment, Endpoint
from apps.registry.models import ModelVersion
from infrastructure.execution.cleanup_backends import DockerProjectCleanupBackend


class FakeStorage:
    def __init__(self):
        self.prefixes = []

    def delete_prefix(self, prefix):
        self.prefixes.append(prefix)


@pytest.mark.django_db
def test_delete_endpoint_marks_the_entire_project_deleting_and_enqueues_cleanup(
    django_capture_on_commit_callbacks, monkeypatch
):
    owner = get_user_model().objects.create_user("delete-owner@example.com", "password123")
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
    owner = get_user_model().objects.create_user("manifest-owner@example.com", "password123")
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

    assert manifest["image_uris"] == sorted(
        [
            f"{repository}:v1",
            f"{repository}:v2",
            f"{repository}:build-{old_build.public_id}",
            f"{repository}:build-{new_build.public_id}",
        ]
    )
    # A stopped deployment is still included: project deletion must clean stale runtimes too.
    assert manifest["container_names"] == ["deploy-old"]
    assert new_build.public_id


@pytest.mark.django_db
def test_finalization_deletes_project_s3_prefix_and_database_rows(monkeypatch):
    monkeypatch.setattr("common.redis_client.redis_client", lambda: SimpleNamespace(delete=lambda *keys: None))
    monkeypatch.setattr("apps.catalog.services.deletion.invalidate_model_server_cache", lambda *args: None)
    owner = get_user_model().objects.create_user("finalize-owner@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="Finalize me", deletion_state="deleting", is_active=False)
    version = ModelVersion.objects.create(project=project, version="1")
    build = Build.objects.create(
        project=project,
        version=version,
        flavor="sklearn",
        status="ready",
        image_uri=f"image-{project.public_id}:v1",
    )
    deployment = Deployment.objects.create(version=version, build=build, status="succeeded")
    endpoint = Endpoint.objects.create(
        deployment=deployment,
        public_url="http://example.test",
        runtime_name="deploy-finalize",
    )
    storage = FakeStorage()

    project_id, project_pk = project.public_id, project.pk
    finalize_project_deletion(project, storage=storage)
    assert storage.prefixes == [f"users/{owner.tenant_id}/models/{project_id}"]
    assert not ModelProject.objects.filter(pk=project_pk).exists()
    assert not Deployment.objects.filter(pk=deployment.pk).exists()
    assert not Endpoint.objects.filter(pk=endpoint.pk).exists()
    assert not ModelVersion.objects.filter(pk=version.pk).exists()

    # Verifies the original name is immediately reusable for new projects.
    recreated = ModelProject.objects.create(owner=owner, name="Finalize me")
    assert recreated.pk != project_pk


def test_local_cleanup_uses_docker_sdk_without_a_model_cleaner_container():
    removed = []

    class Containers:
        def get(self, name):
            return SimpleNamespace(remove=lambda force: removed.append(("container", name, force)))

    class Images:
        def remove(self, image, force, noprune):
            removed.append(("image", image, force, noprune))

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


@pytest.mark.django_db
def test_failed_finalization_can_retry_without_affecting_other_project(monkeypatch):
    from apps.catalog.services.deletion import request_project_deletion
    from apps.catalog.tasks import execute_project_deletion

    owner = get_user_model().objects.create_user("retry-cleanup@example.test", "test-password")
    project = ModelProject.objects.create(owner=owner, name="Remove", deletion_state="deleting", is_active=False)
    other = ModelProject.objects.create(owner=owner, name="Keep")
    cleanup = "apps.catalog.services.deletion."
    monkeypatch.setattr(cleanup + "run_project_cleanup", lambda project: {"dispatched": False})
    original = finalize_project_deletion

    def fail(project):
        raise RuntimeError("Storage cleanup unavailable")

    monkeypatch.setattr(cleanup + "finalize_project_deletion", fail)
    with pytest.raises(RuntimeError):
        execute_project_deletion(str(project.public_id))
    project.refresh_from_db()
    assert project.deletion_state == "delete_failed"
    monkeypatch.setattr("apps.catalog.tasks.execute_project_deletion.delay", lambda id: SimpleNamespace(id="retry"))
    request_project_deletion(project)
    monkeypatch.setattr(cleanup + "finalize_project_deletion", lambda project: original(project, storage=FakeStorage()))
    monkeypatch.setattr("common.redis_client.redis_client", lambda: SimpleNamespace(delete=lambda *keys: None))
    monkeypatch.setattr(cleanup + "invalidate_model_server_cache", lambda *args: None)
    assert execute_project_deletion(str(project.public_id)) == "deleted"
    assert ModelProject.objects.filter(pk=other.pk).exists()
    assert execute_project_deletion(str(project.public_id)) == "deleted"
