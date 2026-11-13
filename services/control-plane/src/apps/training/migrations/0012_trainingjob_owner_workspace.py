from django.conf import settings
from django.db import migrations, models
from django.db.models import OuterRef, Subquery
import django.db.models.deletion


def backfill_owners(apps, schema_editor):
    job = apps.get_model("training", "TrainingJob")
    project = apps.get_model("catalog", "ModelProject")
    owner = project.objects.filter(pk=OuterRef("project_id")).values("owner_id")[:1]
    job.objects.using(schema_editor.connection.alias).filter(owner__isnull=True).update(owner_id=Subquery(owner))


class Migration(migrations.Migration):
    dependencies = [
        ("training", "0011_training_workspace"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="trainingjob", name="owner",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE,
                                    related_name="training_jobs", to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(backfill_owners, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="trainingjob", name="owner",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                    related_name="training_jobs", to=settings.AUTH_USER_MODEL),
        ),
    ]
