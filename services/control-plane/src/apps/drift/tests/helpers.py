from apps.ct.models import DatasetSnapshot
from apps.registry.models import ModelVersion
from django.utils import timezone


def create_version_with_reference_snapshot(project, version="1"):
    snapshot = DatasetSnapshot.objects.create(
        project=project,
        role="reference",
        manifest_uri="s3://bucket/reference.csv",
        manifest_checksum="reference-sha256",
        schema_checksum="schema-sha256",
        row_count=100,
        sealed_at=timezone.now(),
    )
    return ModelVersion.objects.create(project=project, version=version, reference_snapshot=snapshot)
