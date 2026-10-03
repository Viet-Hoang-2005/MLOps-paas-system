from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.catalog.models import ModelPreview, ModelProject


@receiver(post_save, sender=ModelProject, dispatch_uid="catalog.create_preview")
def create_project_preview(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        ModelPreview.objects.create(project=instance)
