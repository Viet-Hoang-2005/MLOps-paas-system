from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("deployment", "0005_remove_build_log_tail_remove_build_log_uri")]

    operations = [
        migrations.AddField(
            model_name="build",
            name="argo_stop_confirmed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
