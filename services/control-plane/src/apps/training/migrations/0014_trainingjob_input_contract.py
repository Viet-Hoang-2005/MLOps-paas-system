from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("training", "0013_trainingjob_storage_ownership")]
    operations = [
        migrations.AlterField(model_name="trainingjobcapability", name="purpose", field=models.CharField(choices=[("input_download", "Input download"), ("output_upload", "Output upload"), ("trusted_reporter", "Trusted reporter"), ("cancel_reporter", "Cancellation reporter"), ("tracking", "Tracking reporter"), ("runtime_config", "Runtime configuration")], max_length=40)),
        migrations.AddField(model_name="trainingjob", name="input_contract", field=models.CharField(choices=[("legacy", "Legacy"), ("workspace", "Workspace")], default="legacy", max_length=16)),
        migrations.AddField(model_name="trainingjob", name="workspace_revision", field=models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="trainingjob", name="run_key", field=models.UUIDField(blank=True, editable=False, null=True, unique=True)),
        migrations.AddField(model_name="trainingjob", name="environment_snapshot", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="trainingjob", name="secret_snapshot", field=models.JSONField(blank=True, default=dict, editable=False)),
    ]
