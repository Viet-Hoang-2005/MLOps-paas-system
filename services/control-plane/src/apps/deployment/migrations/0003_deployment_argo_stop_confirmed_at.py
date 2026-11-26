from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("deployment", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="deployment",
            name="argo_stop_confirmed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
