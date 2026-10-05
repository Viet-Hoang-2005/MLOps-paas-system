from apps.production.models import PredictionRecord
from django.shortcuts import get_object_or_404


def latest_production_data(project, limit=100, version_id=None):
    """Return the six stable frontend fields from the owned production table."""
    records = (
        PredictionRecord.objects.filter(project=project).select_related("model_version").order_by("-observed_at", "-id")
    )
    if version_id is not None:
        version = get_object_or_404(project.versions, public_id=version_id)
        records = records.filter(model_version=version)
    if limit is not None:
        records = records[:limit]
    return [
        {
            "id": str(record.public_id),
            "project_id": str(record.project.public_id),
            "model_version_id": str(record.model_version.public_id),
            "timestamp": record.observed_at,
            "features": record.features,
            "prediction": record.prediction,
        }
        for record in records
    ]
