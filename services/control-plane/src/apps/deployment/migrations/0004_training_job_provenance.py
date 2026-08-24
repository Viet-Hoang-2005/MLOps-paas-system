import django.db.models.deletion
from django.db import migrations, models


def snapshot_source_job(apps, schema_editor):
    Build = apps.get_model("deployment", "Build")
    for build in Build.objects.exclude(source_job_id=None).iterator():
        build.source_job_reference = build.source_job.public_id
        build.save(update_fields=["source_job_reference"])


class Migration(migrations.Migration):
    dependencies = [
        ("deployment", "0003_training_build_lifecycle"),
        ("training", "0004_training_job_deletion"),
    ]

    operations = [
        migrations.AddField(
            model_name="build",
            name="source_job_reference",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(snapshot_source_job, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="build",
            name="source_job",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="builds",
                to="training.trainingjob",
            ),
        ),
    ]
