from django.db import migrations, models
from django.utils import timezone


def schedule_registered_builds(apps, schema_editor):
    build = apps.get_model("deployment", "Build")
    build.objects.using(schema_editor.connection.alias).filter(
        version__isnull=False, status="ready", deletion_state="active"
    ).update(registered_storage_cleanup_due_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [("deployment", "0003_deployment_argo_stop_confirmed_at")]

    operations = [
        migrations.AddField(
            model_name="build",
            name="registered_storage_cleanup_due_at",
            field=models.DateTimeField(blank=True, db_index=True, editable=False, null=True),
        ),
        migrations.RunPython(schedule_registered_builds, migrations.RunPython.noop),
    ]
