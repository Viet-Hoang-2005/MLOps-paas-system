import uuid

from django.db import models, router, transaction


class PublicModel(models.Model):
    """Common internal bigint primary key plus externally safe UUID."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        abstract = True


class VersionReferenceModel(PublicModel):
    """Serialize lineage writes with the version's deletion claim."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        from apps.registry.models import ModelVersion
        from common.api.exceptions import Conflict

        version_ids = {getattr(self, field) for field in self.version_reference_fields} - {None}
        database = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=database):
            versions = list(
                ModelVersion.objects.using(database)
                .select_for_update()
                .filter(pk__in=version_ids)
                .order_by("pk")
                .values_list("deletion_requested", flat=True)
            )
            if len(versions) != len(version_ids) or any(versions):
                raise Conflict("Continuous training cannot reference a model version being deleted.")
            return super().save(*args, **kwargs)
