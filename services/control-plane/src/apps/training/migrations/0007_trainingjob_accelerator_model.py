from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("training", "0006_trainingjob_mlflow_artifacts_uri")]

    operations = [
        migrations.AddField(
            model_name="trainingjob",
            name="accelerator_model",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
    ]
