from django.db import IntegrityError, transaction

from apps.catalog.models import ModelProject
from common.api.exceptions import Conflict


def save_project_metadata(*, actor, validated_data, project=None, storage=None):
    data = dict(validated_data)
    name = data.get("name", project.name if project else "")
    duplicate = ModelProject.objects.filter(owner=actor, name=name)
    if project is not None:
        duplicate = duplicate.exclude(pk=project.pk)
    if duplicate.exists():
        raise Conflict(f"A model project named {name} already exists.")
    try:
        with transaction.atomic():
            if project is None:
                project = ModelProject.objects.create(owner=actor, **data)
                project.current_draft
            else:
                update_fields = ["updated_at"]
                for field, value in data.items():
                    if hasattr(project, field):
                        setattr(project, field, value)
                        update_fields.append(field)
                project.save(update_fields=list(set(update_fields)))
    except IntegrityError as exc:
        if "project_owner_name_unique" in str(exc) or "catalog_modelproject.owner_id" in str(exc):
            raise Conflict(f"A model project named {name} already exists.") from exc
        raise
    return project

def update_project_metadata(*, project, **kwargs):
    """Update project metadata without touching versions."""
    for field, value in kwargs.items():
        if hasattr(project, field):
            setattr(project, field, value)
    project.save()
    return project
