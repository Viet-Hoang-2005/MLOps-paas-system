from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("deployment", "0006_build_deletion_state"),
        ("registry", "0003_remove_modelversion_registry_source_job_unique_and_more"),
    ]
    operations = [
        migrations.AddField(
            model_name="endpoint", name="health_check_lease_until",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="endpoint", name="health_check_token",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AlterField(
            model_name="deployment", name="status",
            field=models.CharField(choices=[
                ("pending", "Pending"), ("deploying", "Deploying"), ("succeeded", "Succeeded"),
                ("failed", "Failed"), ("stopped", "Stopped"), ("unconfirmed", "Unconfirmed"),
            ], default="pending", max_length=30),
        ),
        migrations.AlterField(
            model_name="endpoint", name="health_status",
            field=models.CharField(choices=[
                ("unknown", "Unknown"), ("healthy", "Healthy"), ("unhealthy", "Unhealthy"),
            ], default="unknown", max_length=30),
        ),
        migrations.AddConstraint(
            model_name="deployment", constraint=models.CheckConstraint(
                check=models.Q(status__in=("pending", "deploying", "succeeded", "failed", "stopped", "unconfirmed")),
                name="deployment_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="endpoint", constraint=models.CheckConstraint(
                check=models.Q(health_status__in=("unknown", "healthy", "unhealthy")), name="endpoint_health_valid",
            ),
        ),
    ]
