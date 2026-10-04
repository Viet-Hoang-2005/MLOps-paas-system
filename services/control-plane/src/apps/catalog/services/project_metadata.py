from django.db import IntegrityError, transaction

from apps.catalog.models import ModelProject
from apps.deployment.services.cache import invalidate_model_server_cache
from common.api.exceptions import Conflict


def save_project_metadata(*, actor, validated_data, project=None, storage=None):
    """Project metadata is immediate; artifact edits belong exclusively to Preview."""
    data = {key: value for key, value in validated_data.items() if key in {"name", "description", "access_mode"}}
    name = data.get("name", project.name if project else "")
    duplicate = ModelProject.objects.filter(owner=actor, name=name, is_active=True)
    if project is not None:
        duplicate = duplicate.exclude(pk=project.pk)
    if duplicate.exists():
        raise Conflict(f"A model project named {name} already exists.")
    try:
        with transaction.atomic():
            if project is None:
                return ModelProject.objects.create(owner=actor, **data)
            project = ModelProject.objects.select_for_update().get(pk=project.pk)
            if project.deletion_state != "active":
                raise Conflict("This project is being deleted.")
            for field, value in data.items():
                setattr(project, field, value)
            project.save(update_fields=[*data, "updated_at"])
            ids = list(project.versions.values_list("public_id", flat=True))
            transaction.on_commit(lambda: [invalidate_model_server_cache(str(value)) for value in ids])
    except IntegrityError as exc:
        if "project_owner_active_name_unique" in str(exc) or "catalog_modelproject.owner_id" in str(exc):
            raise Conflict(f"A model project named {name} already exists.") from exc
        raise
    return project
