from pathlib import Path

from common.api.exceptions import Conflict
from django.db import IntegrityError, transaction
from infrastructure.storage import S3Storage

from apps.catalog.models import ModelProject
from apps.catalog.services.workspace import save_workspace_file


def _replace_attachment(*, project, kind, uploaded_file, storage):
    if uploaded_file is None:
        return
    old_assets = list(project.workspace_assets.filter(kind=kind))
    filename = Path(uploaded_file.name).name
    saved = save_workspace_file(
        project=project,
        kind=kind,
        relative_path=filename,
        uploaded_file=uploaded_file,
        storage=storage,
    )
    for asset in old_assets:
        if asset.pk == saved.pk:
            continue
        try:
            storage.delete(asset.s3_uri)
        except Exception:  # pragma: no cover - project deletion also removes the prefix
            pass
        asset.delete()


def save_project_metadata(*, actor, validated_data, project=None, storage=None):
    storage = storage or S3Storage()
    data = dict(validated_data)
    source_code_file = data.pop("source_code_file", None)
    reference_data_file = data.pop("reference_data_file", None)
    duplicate = ModelProject.objects.filter(owner=actor, name=data["name"])
    if project is not None:
        duplicate = duplicate.exclude(pk=project.pk)
    if duplicate.exists():
        raise Conflict(f"A model project named {data['name']} already exists.")
    try:
        with transaction.atomic():
            if project is None:
                project = ModelProject.objects.create(owner=actor, **data)
            else:
                for field, value in data.items():
                    setattr(project, field, value)
                project.save(update_fields=["name", "description", "access_mode", "updated_at"])
            _replace_attachment(project=project, kind="code", uploaded_file=source_code_file, storage=storage)
            _replace_attachment(project=project, kind="data", uploaded_file=reference_data_file, storage=storage)
    except IntegrityError as exc:
        if "project_owner_name_unique" in str(exc) or "catalog_modelproject.owner_id" in str(exc):
            raise Conflict(f"A model project named {data['name']} already exists.") from exc
        raise
    return project
