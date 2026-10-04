from pathlib import PurePosixPath

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.catalog.models import WorkspaceAsset
from common.api.exceptions import Conflict
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import workspace_prefix


def save_workspace_file(*, project, kind, relative_path, uploaded_file, storage=None):
    storage = storage or S3Storage()
    path = PurePosixPath(relative_path)
    if not relative_path or path.is_absolute() or ".." in path.parts or "\\" in relative_path:
        raise ValidationError({"relative_path": "Use a safe relative workspace path."})
    with transaction.atomic():
        project = type(project).objects.select_for_update().get(pk=project.pk)
        if project.deletion_state != "active":
            raise Conflict("This project is being deleted.")
        key = f"{workspace_prefix(project.owner.tenant_id, project.public_id, kind)}{path.as_posix()}"
        stored = storage.put(key, uploaded_file, uploaded_file.content_type or "application/octet-stream")
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


def delete_workspace_file(*, project, kind, relative_path, storage=None):
    with transaction.atomic():
        project = type(project).objects.select_for_update().get(pk=project.pk)
        if project.deletion_state != "active":
            raise Conflict("This project is being deleted.")
        asset = project.workspace_assets.filter(kind=kind, relative_path=relative_path).first()
        if asset:
            (storage or S3Storage()).delete(asset.s3_uri)
            asset.delete()
