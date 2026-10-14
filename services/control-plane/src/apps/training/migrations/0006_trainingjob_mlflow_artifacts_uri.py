from django.db import migrations


def move_mlflow_uri_to_artifacts_root(apps, schema_editor):
    TrainingJob = apps.get_model("training", "TrainingJob")
    for job in TrainingJob.objects.exclude(mlflow_artifact_uri="").iterator():
        if job.mlflow_artifact_uri.endswith("/mlflow/"):
            job.mlflow_artifact_uri = f"{job.mlflow_artifact_uri}artifacts/"
            job.save(update_fields=["mlflow_artifact_uri"])


def restore_mlflow_uri_root(apps, schema_editor):
    TrainingJob = apps.get_model("training", "TrainingJob")
    for job in TrainingJob.objects.exclude(mlflow_artifact_uri="").iterator():
        if job.mlflow_artifact_uri.endswith("/mlflow/artifacts/"):
            job.mlflow_artifact_uri = job.mlflow_artifact_uri.removesuffix("artifacts/")
            job.save(update_fields=["mlflow_artifact_uri"])


class Migration(migrations.Migration):
    dependencies = [("training", "0005_alter_trainingjobcapability_purpose_trainingjobparam_and_more")]

    operations = [migrations.RunPython(move_mlflow_uri_to_artifacts_root, restore_mlflow_uri_root)]
