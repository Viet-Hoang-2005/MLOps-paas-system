from celery import shared_task


@shared_task(ignore_result=True)
def cleanup_model_version(version_id):
    from apps.registry.models import ModelVersion
    from apps.registry.services.deletion import delete_model_version

    version = ModelVersion.objects.filter(public_id=version_id, deletion_requested=True).first()
    if version is None:
        return "missing"
    delete_model_version(version)
    return "deleted"
