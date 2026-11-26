from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("drift", "0003_driftmonitor_deletion_requested"),
    ]

    operations = [
        migrations.AddField(
            model_name="driftrun",
            name="argo_stop_confirmed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
