from django.db import transaction
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import workspace_prefix

from apps.catalog.models import WorkspaceAsset


def save_workspace_file(*, project, kind, relative_path, uploaded_file, storage=None):
    storage = storage or S3Storage()
    key = f"{workspace_prefix(project.owner.tenant_id, project.public_id, kind)}{relative_path.strip('/')}"
    stored = storage.put(key, uploaded_file, uploaded_file.content_type or "application/octet-stream")
    with transaction.atomic():
        asset, _ = WorkspaceAsset.objects.update_or_create(
            project=project,
            kind=kind,
            relative_path=relative_path,
            defaults={
                "s3_uri": stored.uri,
                "checksum": stored.checksum,
                "size_bytes": stored.size_bytes,
                "content_type": stored.content_type,
            },
        )
    return asset
