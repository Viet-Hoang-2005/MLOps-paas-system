import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("deployment", "0002_initial"),
        ("training", "0003_training_build_lifecycle"),
    ]

    operations = [
        migrations.AddField(
            model_name="build",
            name="source_job",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="builds",
                to="training.trainingjob",
            ),
        ),
        migrations.AlterField(
            model_name="buildinputasset",
            name="kind",
            field=models.CharField(
                choices=[
                    ("source_artifact", "Source Artifact"),
                    ("training_output", "Training Output"),
                    ("label_mapping", "Label Mapping"),
                    ("metrics", "Metrics"),
                    ("params", "Parameters"),
                    ("model_insights", "Model Insights"),
                    ("feature_importance", "Feature Importance"),
                    ("input_schema", "Input Schema"),
                ],
                max_length=40,
            ),
        ),
        migrations.AddConstraint(
            model_name="build",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("source_job__isnull", False),
                    ("status__in", ("pending", "queued", "building", "ready")),
                ),
                fields=("source_job",),
                name="build_active_source_job_unique",
            ),
        ),
    ]
