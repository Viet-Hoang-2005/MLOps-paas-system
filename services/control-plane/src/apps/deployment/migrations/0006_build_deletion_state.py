from django.db import migrations, models


def stamp_completed_builds(apps, schema_editor):
    Build = apps.get_model("deployment", "Build")
    Build.objects.using(schema_editor.connection.alias).filter(
        status__in=("ready", "failed"), completed_at__isnull=False
    ).update(execution_completed_at=models.F("completed_at"))


class Migration(migrations.Migration):
    dependencies = [("deployment", "0005_buildinputasset_metadata")]

    operations = [
        migrations.AddField(
            model_name="build",
            name="deletion_state",
            field=models.CharField(
                choices=[("active", "Active"), ("deleting", "Deleting"), ("delete_failed", "Delete Failed")],
                default="active",
                max_length=20,
            ),
        ),
        migrations.AddField(model_name="build", name="deletion_error", field=models.TextField(blank=True)),
        migrations.AddField(
            model_name="build", name="execution_completed_at", field=models.DateTimeField(blank=True, null=True)
        ),
        migrations.RunPython(stamp_completed_builds, migrations.RunPython.noop),
    ]
