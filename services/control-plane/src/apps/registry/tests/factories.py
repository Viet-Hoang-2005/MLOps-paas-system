from apps.ct.models import DatasetSnapshot
from apps.registry.models import ModelVersion


def create_model_version(project, version="1", **fields):
    reference_snapshot = fields.pop("reference_snapshot", None)
    if reference_snapshot is None:
        reference_snapshot = DatasetSnapshot.objects.create(
            project=project,
            role="reference",
            manifest_uri=f"s3://test-bucket/{project.public_id}/{version}/reference.csv",
            manifest_checksum="reference-checksum",
            schema_checksum="schema-checksum",
            row_count=10,
        )
    return ModelVersion.objects.create(
        project=project,
        version=str(version),
        reference_snapshot=reference_snapshot,
        **fields,
    )
