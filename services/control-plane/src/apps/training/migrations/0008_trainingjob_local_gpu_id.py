from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("training", "0007_trainingjob_accelerator_model")]
    operations = [migrations.AddField(model_name="trainingjob", name="local_gpu_id",
                                      field=models.CharField(blank=True, default="", max_length=80))]
