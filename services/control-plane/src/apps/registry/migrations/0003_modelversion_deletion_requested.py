from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="modelversion",
            name="deletion_requested",
            field=models.BooleanField(default=False),
        ),
    ]
