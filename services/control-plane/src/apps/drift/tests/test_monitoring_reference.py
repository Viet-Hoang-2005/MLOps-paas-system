import pytest
from django.contrib.auth import get_user_model

from apps.catalog.models import ModelProject
from apps.ct.models import DatasetSnapshot
from apps.drift.models import DriftMonitor
from apps.registry.models import ModelVersion


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user("be-drift-owner@example.com", "password123")


@pytest.fixture
def project(owner):
    return ModelProject.objects.create(
        owner=owner,
        name="Credit Drift Monitoring Project",
        description="Testing monitoring reference lineage",
        task_domain="binary_classification",
    )


@pytest.mark.django_db
def test_monitoring_always_queries_version_reference(project):
    snap1 = DatasetSnapshot.objects.create(
        project=project,
        role="reference",
        manifest_uri="s3://test-bucket/ref1.parquet",
        manifest_checksum="sha256:ref1",
        schema_checksum="sha256:s1",
        row_count=1000,
    )
    snap2 = DatasetSnapshot.objects.create(
        project=project,
        role="reference",
        manifest_uri="s3://test-bucket/ref2.parquet",
        manifest_checksum="sha256:ref2",
        schema_checksum="sha256:s2",
        row_count=2500,
    )

    v1 = ModelVersion.objects.create(project=project, version="v1.0.0", reference_snapshot=snap1)
    v2 = ModelVersion.objects.create(project=project, version="v2.0.0", reference_snapshot=snap2)

    monitor_v2 = DriftMonitor.objects.create(
        version=v2,
        name="Production Drift Monitor v2",
        reference_snapshot=v2.reference_snapshot,
    )

    assert monitor_v2.reference_snapshot == snap2
    assert monitor_v2.reference_snapshot.row_count == 2500
    assert monitor_v2.reference_snapshot != snap1
    assert monitor_v2.version == v2
