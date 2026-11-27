from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("drift", "0007_remove_driftmonitor_detector_config_and_more")]

    operations = [
        migrations.AddField(
            model_name="driftmonitor",
            name="deletion_cleanup_due_at",
            field=models.DateTimeField(blank=True, db_index=True, editable=False, null=True),
        ),
    ]
