from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("training", "0015_training_storage_copy")]
    operations = [
        migrations.AddField(model_name="trainingjob", name="build_requirements_text", field=models.TextField(blank=True, null=True)),
        migrations.AlterField(model_name="trainingoutput", name="kind", field=models.CharField(choices=[("model", "Model"), ("metric", "Metric"), ("insight", "Insight"), ("source_code", "Source Code"), ("reference_data", "Reference Data"), ("file", "File"), ("label_mapping", "Label mapping"), ("input_schema", "Input schema")], default="file", max_length=30)),
    ]
