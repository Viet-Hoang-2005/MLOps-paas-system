import django.db.models.deletion
from django.db import migrations, models


def snapshot_source_job(apps, schema_editor):
    ModelVersion = apps.get_model("registry", "ModelVersion")
    for version in ModelVersion.objects.exclude(source_job_id=None).iterator():
        version.source_job_reference = version.source_job.public_id
        version.save(update_fields=["source_job_reference"])


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0001_initial"),
        ("training", "0004_training_job_deletion"),
    ]

    operations = [
        migrations.AddField(
            model_name="modelversion",
            name="source_job_reference",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(snapshot_source_job, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="modelversion",
            name="source_job",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="registered_versions",
                to="training.trainingjob",
            ),
        ),
    ]
