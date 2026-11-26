from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("drift", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="driftmonitor",
            name="deletion_requested",
            field=models.BooleanField(default=False),
        ),
    ]
