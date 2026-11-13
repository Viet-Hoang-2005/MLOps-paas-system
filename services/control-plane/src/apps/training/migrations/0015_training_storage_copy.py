from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("training", "0014_trainingjob_input_contract")]
    operations = [
        migrations.CreateModel(name="TrainingStorageCopy", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("source_uri", models.CharField(max_length=1024)),
            ("destination_uri", models.CharField(max_length=1024)),
            ("source_etag", models.CharField(max_length=160)),
            ("checksum", models.CharField(max_length=64)),
            ("verified_at", models.DateTimeField(auto_now=True)),
            ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="storage_copies", to="training.trainingjob")),
        ]),
        migrations.AddConstraint(model_name="trainingstoragecopy", constraint=models.UniqueConstraint(fields=("job", "source_uri"), name="training_storage_copy_unique")),
    ]
