from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("training", "0002_trainingjobcapability")]

    operations = [
        migrations.AddField(
            model_name="trainingjob",
            name="model_flavor",
            field=models.CharField(
                choices=[
                    ("sklearn", "Scikit-learn"),
                    ("xgboost", "XGBoost"),
                    ("pytorch", "PyTorch"),
                    ("tensorflow", "TensorFlow"),
                ],
                default="sklearn",
                max_length=40,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="trainingjob",
            name="outputs_purged_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="trainingjob",
            name="accelerator_type",
            field=models.CharField(
                choices=[("none", "None"), ("gpu", "GPU")],
                default="none",
                max_length=20,
            ),
        ),
    ]
