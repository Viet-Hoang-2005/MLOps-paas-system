from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.ct.models.evidence import DatasetSnapshot, EvidenceWindow
from apps.ct.models.policy import MaintenancePolicy
from apps.deployment.builds.tasks import register_build
from apps.deployment.models import Build, Deployment, Endpoint
from apps.deployment.serving.rollout import request_deployment
from apps.drift.models import DriftMonitor, DriftRun
from apps.drift.monitors.reference import create_monitor
from apps.drift.runs.lifecycle import request_run
from apps.registry.models import ModelArtifact, ModelVersion, RegistryAlias
from apps.registry.versions.tasks import cleanup_model_version
from apps.training.tests.factories import training_job as make_training_job
from common.api.exceptions import Conflict, ServiceUnavailable


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("failure", [None, "stop", "image", "storage", "argo-unconfirmed"])
def test_delete_version_removes_runtime_monitors_s3_image_and_unlocks_build(monkeypatch, failure):
    owner = get_user_model().objects.create_user("reg-del@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="Delete Version Project")
    job = make_training_job(project=project, status="completed")
    version = ModelVersion.objects.create(project=project, source_job=job, version="1")
    artifact_uri = (
        f"s3://bucket/users/{owner.tenant_id}/models/{project.public_id}/versions/{version.public_id}/model.joblib"
    )
    ModelArtifact.objects.create(version=version, kind="model", name="model.joblib", uri=artifact_uri)

    build = Build.objects.create(
        project=project,
        source_job=job,
        version=version,
        flavor="sklearn",
        status="ready",
        registration_status="registered",
        image_uri=f"image-{project.public_id}:{version.public_id}",
        image_digest="sha256:old-image",
    )
    deployment = Deployment.objects.create(version=version, build=build, backend="docker", status="succeeded")
    Endpoint.objects.create(
        deployment=deployment, public_url="http://localhost:5002/p", runtime_name=f"deploy-{deployment.public_id}"
    )
    project.active_deployment = deployment
    project.save(update_fields=["active_deployment"])
    RegistryAlias.objects.create(project=project, version=version, name="champion")

    monitor = DriftMonitor.objects.create(
        version=version,
        name="m1",
        reference_uri=f"s3://bucket/users/{owner.tenant_id}/models/{project.public_id}/drift/ref.csv",
    )
    run = DriftRun.objects.create(
        monitor=monitor,
        status="completed",
        idempotency_key="vdel-run-1",
        report_html_uri=f"s3://bucket/users/{owner.tenant_id}/models/{project.public_id}/drift/{monitor.public_id}/r/report.html",
    )

    backend = Mock()
    monkeypatch.setattr(
        "apps.registry.versions.deletion.deployment_backend",
        lambda _backend: backend,
    )
    invalidate_cache = Mock()
    monkeypatch.setattr("apps.registry.versions.deletion.invalidate_model_server_cache", invalidate_cache)
    remove_image = Mock()
    monkeypatch.setattr("apps.registry.versions.deletion._remove_build_image", remove_image)

    storage = Mock(bucket="bucket")
    monkeypatch.setattr("apps.registry.versions.deletion.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.drift.monitors.deletion.S3Storage", lambda: storage)
    redis_mock = Mock()
    monkeypatch.setattr("apps.registry.versions.deletion.redis_client", lambda: redis_mock)
    monkeypatch.setattr("apps.drift.monitors.deletion.redis_client", lambda: redis_mock)

    client = APIClient()
    client.force_authenticate(owner)
    url = f"/api/model-versions/{version.public_id}/"
    dispatched_after_commit = []

    def capture_dispatch(**_):
        dispatched_after_commit.append(
            not connection.in_atomic_block and ModelVersion.objects.get(pk=version.pk).deletion_requested
        )

    dispatch = Mock(side_effect=capture_dispatch)
    monkeypatch.setattr(cleanup_model_version, "apply_async", dispatch)
    response = client.delete(url)
    assert response.status_code == 202
    assert response.data["deletion_requested"] is True
    dispatch.assert_called_once_with(args=[str(version.public_id)], retry=False)
    assert dispatched_after_commit == [True]
    assert client.get(url).data["deletion_requested"] is True
    assert client.delete(url).status_code == 202
    dispatch.assert_called_once()
    backend.stop.assert_not_called()
    remove_image.assert_not_called()
    storage.delete_prefix.assert_not_called()
    invalidate_cache.assert_not_called()
    if failure is None:

        def assert_writes_blocked():
            assert ModelVersion.objects.get(pk=version.pk).deletion_requested
            with pytest.raises(Conflict, match="model version is being deleted"):
                request_deployment(build, "docker")
            with pytest.raises(Conflict, match="model version is being deleted"):
                create_monitor(data={"version": version, "name": "late"}, backend="docker", storage=storage)
            with pytest.raises(Conflict, match="model version is being deleted"):
                request_run(monitor)
            with pytest.raises(Conflict, match="Continuous training"):
                EvidenceWindow.objects.create(champion=version)

        def during_cleanup(_deployment):
            if connection.vendor != "postgresql":
                assert_writes_blocked()
                return

            def check_from_other_connection():
                try:
                    assert_writes_blocked()
                finally:
                    connections.close_all()

            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(check_from_other_connection).result(timeout=10)

        backend.stop.side_effect = during_cleanup
    if failure:
        if failure == "argo-unconfirmed":
            Deployment.objects.filter(pk=deployment.pk).update(backend="argo")
            backend.stop.return_value = {"dispatched": True}
        elif failure == "stop":
            backend.stop.side_effect = TimeoutError("runtime unavailable")
        elif failure == "image":
            remove_image.side_effect = TimeoutError("registry unavailable")
        else:
            version_prefix = artifact_uri.removeprefix("s3://bucket/").rsplit("/", 1)[0] + "/"

            def fail_on_version_prefix(prefix):
                if prefix == version_prefix:
                    raise TimeoutError("storage unavailable")

            storage.delete_prefix.side_effect = fail_on_version_prefix
        with pytest.raises(ServiceUnavailable):
            cleanup_model_version.run(str(version.public_id))
        assert ModelVersion.objects.filter(pk=version.pk, deletion_requested=True, artifacts__uri=artifact_uri).exists()
        assert Deployment.objects.filter(pk=deployment.pk, endpoint__isnull=False).exists()
        assert RegistryAlias.objects.filter(version=version).exists()
        assert DriftRun.objects.filter(pk=run.pk, monitor=monitor).exists()
        build.refresh_from_db()
        assert build.version_id == version.pk
        assert build.image_uri

        backend.stop.side_effect = None
        backend.stop.return_value = {"confirmed": True}
        remove_image.side_effect = None
        storage.delete_prefix.side_effect = None

    assert cleanup_model_version.run(str(version.public_id)) == "deleted"
    assert client.get(url).status_code == 404
    assert not ModelVersion.objects.filter(pk=version.pk).exists()
    assert not Deployment.objects.filter(pk=deployment.pk).exists()
    assert not RegistryAlias.objects.filter(project=project).exists()
    assert not DriftMonitor.objects.filter(pk=monitor.pk).exists()
    project.refresh_from_db()
    assert project.active_deployment is None

    build.refresh_from_db()
    assert build.version is None
    assert build.registration_status == "unregistered"
    assert build.image_uri == ""
    assert build.image_digest == ""
    dispatch = Mock()
    monkeypatch.setattr(register_build, "delay", dispatch)
    response = client.post(f"/api/builds/{build.public_id}/register/")
    assert response.status_code == 409
    assert "Rebuild" in str(response.data)
    dispatch.assert_not_called()
    assert register_build.run(str(build.public_id)) == "image_missing"

    backend.stop.assert_called_with(deployment)
    assert backend.stop.call_count == (2 if failure else 1)
    invalidate_cache.assert_called_with(str(version.public_id))
    assert remove_image.call_args.args[0].image_uri == f"image-{project.public_id}:{version.public_id}"
    assert storage.delete_prefix.called


@pytest.mark.django_db
def test_delete_version_preserves_resources_referenced_by_ct_when_disabled(monkeypatch, settings):
    settings.CT_ENABLED = False
    owner = get_user_model().objects.create_user("reg-ct@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="CT lineage")
    version = ModelVersion.objects.create(project=project, version="1")
    build = Build.objects.create(project=project, version=version, status="ready", image_uri="model:v1")
    deployment = Deployment.objects.create(version=version, build=build, status="succeeded")
    project.active_deployment = deployment
    project.save(update_fields=["active_deployment"])
    artifact = ModelArtifact.objects.create(version=version, kind="model", name="model.pkl", uri="s3://bucket/model.pkl")
    policy = MaintenancePolicy.objects.create(project=project, version=1, policy_kind="b0", checksum="policy")
    snapshot = DatasetSnapshot.objects.create(project=project, role="reference", manifest_uri="s3://bucket/reference.json")
    now = timezone.now()
    window = EvidenceWindow.objects.create(
        project=project,
        champion=version,
        policy=policy,
        reference_snapshot=snapshot,
        ordinal=1,
        starts_at=now,
        ends_at=now + timedelta(hours=1),
    )

    backend = Mock()
    remove_image = Mock()
    storage = Mock(bucket="bucket")
    invalidate_cache = Mock()
    monkeypatch.setattr("apps.registry.versions.deletion.deployment_backend", backend)
    monkeypatch.setattr("apps.registry.versions.deletion._remove_build_image", remove_image)
    monkeypatch.setattr("apps.registry.versions.deletion.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.registry.versions.deletion.invalidate_model_server_cache", invalidate_cache)
    monkeypatch.setattr("apps.registry.versions.deletion.redis_client", Mock())

    client = APIClient()
    client.force_authenticate(owner)
    response = client.delete(f"/api/model-versions/{version.public_id}/")

    assert response.status_code == 409
    assert "continuous training lineage" in str(response.data)
    version.refresh_from_db()
    project.refresh_from_db()
    assert not version.deletion_requested
    assert project.active_deployment_id == deployment.pk
    assert ModelArtifact.objects.filter(pk=artifact.pk, uri=artifact.uri).exists()
    assert EvidenceWindow.objects.filter(pk=window.pk, champion=version).exists()
    backend.assert_not_called()
    remove_image.assert_not_called()
    storage.delete_prefix.assert_not_called()
    storage.delete.assert_not_called()
    invalidate_cache.assert_not_called()


@pytest.mark.django_db
def test_delete_version_requires_owner(monkeypatch):
    owner = get_user_model().objects.create_user("reg-owner@example.com", "password123")
    other = get_user_model().objects.create_user("reg-other@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="Tenant Scoped")
    version = ModelVersion.objects.create(project=project, version="1")

    client = APIClient()
    client.force_authenticate(other)
    assert client.delete(f"/api/model-versions/{version.public_id}/").status_code == 404
