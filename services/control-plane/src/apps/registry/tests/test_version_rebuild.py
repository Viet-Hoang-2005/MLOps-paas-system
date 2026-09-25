from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.ct.models import DatasetSnapshot
from apps.deployment.models import Deployment, Endpoint
from apps.registry.models import ModelArtifact, ModelVersion
from apps.registry.services.versions import (
    register_successful_build,
    request_version_rebuild,
    set_alias,
)


class FakeStorage:
    def __init__(self):
        self.copies = []

    def copy(self, source_uri, destination_key):
        self.copies.append((source_uri, destination_key))
        return SimpleNamespace(
            uri=f"s3://bucket/{destination_key}",
            checksum="copied-checksum",
            size_bytes=100,
            content_type="application/octet-stream",
        )

    def delete_prefix(self, prefix):
        pass


class FakeImageRegistry:
    def promote(self, *, build, version, image_uri, image_digest=""):
        return f"harbor.local/user/{version.project.name}:{version.version}", image_digest or "sha256:rebuild"


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user("rebuild-owner@example.com", "password123")


@pytest.fixture
def project(owner):
    return ModelProject.objects.create(owner=owner, name="Fraud Detection")


@pytest.fixture
def reference_snapshot(project):
    return DatasetSnapshot.objects.create(
        project=project,
        role="reference",
        manifest_uri="s3://bucket/data/ref.parquet",
        manifest_checksum="sha256:ref123",
        schema_checksum="sha256:schema123",
    )


@pytest.fixture
def v1_with_artifacts(project, reference_snapshot):
    v1 = ModelVersion.objects.create(
        project=project,
        version="1",
        reference_snapshot=reference_snapshot,
    )
    ModelArtifact.objects.create(
        version=v1,
        kind="model",
        name="model.joblib",
        uri="s3://bucket/models/v1/model.joblib",
        checksum="sha256:model1",
        size_bytes=500,
    )
    ModelArtifact.objects.create(
        version=v1,
        kind="reference_data",
        name="reference.parquet",
        uri="s3://bucket/models/v1/reference.parquet",
        checksum="sha256:ref1",
        size_bytes=300,
    )
    ModelArtifact.objects.create(
        version=v1,
        kind="source_code",
        name="source.py",
        uri="s3://bucket/models/v1/source.py",
        checksum="sha256:src1",
        size_bytes=200,
    )
    return v1


@pytest.mark.django_db
def test_evolution_rebuild_clones_all_artifacts_and_preserves_reference_snapshot(
    owner, project, reference_snapshot, v1_with_artifacts, monkeypatch
):
    storage = FakeStorage()
    queued = []
    from apps.deployment.services import builds as build_service

    monkeypatch.setattr(
        build_service.execute_build,
        "delay",
        lambda build_id: queued.append(build_id) or SimpleNamespace(id="task-rebuild"),
    )

    # Establish initial draft
    draft = project.current_draft
    draft.name = "Untouched Draft"
    draft.revision = 3
    draft.status = "draft"
    draft.save()

    build = request_version_rebuild(
        version=v1_with_artifacts,
        actor=owner,
        backend="docker",
        storage=storage,
    )

    assert build.source_kind == "model_version"
    assert build.source_version == v1_with_artifacts
    assert build.project == project
    assert build.status in ("pending", "queued")

    # Verify all 3 input assets were copied and created
    assert build.input_assets.count() == 3
    assert build.input_assets.filter(kind="model", name="model.joblib").exists()
    assert build.input_assets.filter(kind="reference_data", name="reference.parquet").exists()
    assert build.input_assets.filter(kind="source_code", name="source.py").exists()

    # Register build as successful to create v2
    registered_build = register_successful_build(
        build=build,
        image_uri="build-temp:latest",
        storage=storage,
        image_registry=FakeImageRegistry(),
    )

    v2 = registered_build.version
    assert v2 is not None
    assert v2.version == "2"
    assert build.source_version == v1_with_artifacts
    assert v2.reference_snapshot == reference_snapshot
    assert v2.reference_snapshot.role == "reference"

    # Verify draft remains completely untouched
    draft.refresh_from_db()
    assert draft.name == "Untouched Draft"
    assert draft.revision == 3
    assert draft.status == "draft"


@pytest.mark.django_db
def test_rebuild_api_endpoint_authorization(owner, v1_with_artifacts, monkeypatch):
    from apps.deployment.services import builds as build_service

    monkeypatch.setattr(
        build_service.execute_build,
        "delay",
        lambda build_id: SimpleNamespace(id="task-rebuild"),
    )
    monkeypatch.setattr(
        "apps.registry.services.versions.S3Storage",
        FakeStorage,
    )

    client = APIClient()
    client.force_authenticate(owner)

    response = client.post(f"/api/registry/versions/{v1_with_artifacts.public_id}/rebuild/")
    assert response.status_code == 201
    assert "id" in response.data

    other = get_user_model().objects.create_user("other-rebuild@example.com", "password123")
    client.force_authenticate(other)
    forbidden_response = client.post(f"/api/registry/versions/{v1_with_artifacts.public_id}/rebuild/")
    assert forbidden_response.status_code == 404


@pytest.mark.django_db
def test_production_alias_enforces_healthy_deployment(owner, project, v1_with_artifacts):
    # Attempting to assign 'production' alias without healthy deployment must fail
    with pytest.raises(ValidationError, match="has no healthy active deployment"):
        set_alias(
            project=project,
            actor=owner,
            name="production",
            version=v1_with_artifacts,
        )

    # Non-production alias (e.g. 'staging' or 'candidate') does not require healthy deployment
    staging_alias = set_alias(
        project=project,
        actor=owner,
        name="staging",
        version=v1_with_artifacts,
    )
    assert staging_alias.name == "staging"
    assert staging_alias.version == v1_with_artifacts

    # Create unhealthy deployment
    from apps.deployment.models import Build

    build = Build.objects.create(project=project, source_version=v1_with_artifacts, flavor="sklearn")
    deployment = Deployment.objects.create(
        project=project,
        version=v1_with_artifacts,
        build=build,
        target="production",
        status="deploying",
    )
    with pytest.raises(ValidationError, match="has no healthy active deployment"):
        set_alias(
            project=project,
            actor=owner,
            name="production",
            version=v1_with_artifacts,
        )

    # Make deployment healthy and attach healthy endpoint
    deployment.status = "healthy"
    deployment.save()
    Endpoint.objects.create(
        deployment=deployment,
        public_url="https://model.example.com",
        health_status="healthy",
    )

    # Now setting production alias must succeed
    prod_alias = set_alias(
        project=project,
        actor=owner,
        name="production",
        version=v1_with_artifacts,
    )
    assert prod_alias.name == "production"
    assert prod_alias.version == v1_with_artifacts
