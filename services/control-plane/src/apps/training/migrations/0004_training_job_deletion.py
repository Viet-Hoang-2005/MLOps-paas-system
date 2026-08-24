from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("training", "0003_training_build_lifecycle"),
    ]

    operations = [
        migrations.AddField(
            model_name="trainingjob",
            name="deletion_error",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="trainingjob",
            name="deletion_requested_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="trainingjob",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("queued", "Queued"),
                    ("uploading", "Uploading"),
                    ("running", "Running"),
                    ("cancelling", "Cancelling"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="trainingjobcapability",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("output_upload", "Output upload"),
                    ("trusted_reporter", "Trusted reporter"),
                    ("cancel_reporter", "Cancellation reporter"),
                ],
                max_length=40,
            ),
        ),
    ]
