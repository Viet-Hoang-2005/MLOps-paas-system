import pytest
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError

from apps.catalog.models import ModelProject
from apps.ct.models import DatasetSnapshot
from apps.catalog.services.draft import get_project_overview
from apps.deployment.models import Build, Deployment, Endpoint
from apps.registry.models import ModelVersion, RegistryAlias
from apps.registry.services.versions import set_alias


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user("be-gate-owner@example.com", "password123")


@pytest.fixture
def project(owner):
    return ModelProject.objects.create(
        owner=owner,
        name="Production Gate Project",
        description="Testing health-check gated promotion",
        task_domain="binary_classification",
    )


@pytest.mark.django_db
def test_production_alias_only_on_healthy(project, owner):
    snapshots = [DatasetSnapshot.objects.create(
        project=project, role="reference", manifest_uri=f"s3://bucket/ref-{index}", manifest_checksum="m", schema_checksum="s"
    ) for index in (1, 2)]
    v1 = ModelVersion.objects.create(project=project, version="v1.0.0", reference_snapshot=snapshots[0])
    v2 = ModelVersion.objects.create(project=project, version="v2.0.0", reference_snapshot=snapshots[1])

    # 1. v1 triển khai thành công và có endpoint healthy
    build_v1 = Build.objects.create(project=project, version=v1, source_version=v1, status="ready")
    dep_v1 = Deployment.objects.create(
        project=project,
        version=v1,
        build=build_v1,
        target="production",
        status="healthy",
    )
    Endpoint.objects.create(
        deployment=dep_v1,
        public_url="https://models.mlops.local/v1/predict",
        health_status="healthy",
    )
    set_alias(project=project, actor=owner, name="production", version=v1)
    assert RegistryAlias.objects.get(project=project, name="production").version == v1

    # 2. v2 được deploy nhưng fail bài kiểm tra sức khỏe
    build_v2 = Build.objects.create(project=project, version=v2, source_version=v2, status="ready")
    dep_v2 = Deployment.objects.create(
        project=project,
        version=v2,
        build=build_v2,
        target="staging",
        status="failed",
    )
    Endpoint.objects.create(
        deployment=dep_v2,
        public_url="https://models.mlops.local/v2/predict",
        health_status="unhealthy",
    )

    # Cố gắng thăng hạng v2 lên production bị từ chối
    with pytest.raises(ValidationError) as exc:
        set_alias(project=project, actor=owner, name="production", version=v2)
    assert "healthy" in str(exc.value).lower()

    # Alias production trong DB và Tab Present trên giao diện vẫn thuộc quyền v1.0.0
    assert RegistryAlias.objects.get(project=project, name="production").version == v1
    overview = get_project_overview(project=project)
    assert overview["present"]["has_production"] is True
    assert overview["present"]["version"] == "v1.0.0"
