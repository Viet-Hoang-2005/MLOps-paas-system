from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("training", "0008_trainingjob_local_gpu_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="TrainingQuotaReservation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("job_id", models.UUIDField(unique=True)),
                ("resource", models.CharField(max_length=16)),
                ("submitted_at", models.DateTimeField()),
                ("dispatch_deadline_at", models.DateTimeField()),
                ("max_runtime_seconds", models.PositiveIntegerField()),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("runtime_finished_at", models.DateTimeField(blank=True, null=True)),
                ("stopped_at", models.DateTimeField(blank=True, null=True)),
                ("active", models.BooleanField(db_index=True, default=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="training_quota_reservations", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="TrainingQuotaWeek",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("week_start", models.DateTimeField()),
                ("reserved_seconds", models.PositiveIntegerField(default=0)),
                ("used_seconds", models.PositiveIntegerField(default=0)),
                ("reservation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="weeks", to="training.trainingquotareservation")),
            ],
            options={"indexes": [models.Index(fields=["week_start"], name="training_quota_week_idx")]},
        ),
        migrations.AddConstraint(model_name="trainingquotaweek", constraint=models.UniqueConstraint(fields=("reservation", "week_start"), name="training_quota_job_week_unique")),
    ]
