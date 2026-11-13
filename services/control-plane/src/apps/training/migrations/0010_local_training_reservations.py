from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("training", "0009_training_quota")]

    operations = [
        migrations.CreateModel(name="LocalTrainingPool", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("daemon_id", models.CharField(max_length=128, unique=True)),
        ]),
        migrations.CreateModel(name="LocalTrainingReservation", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("job_id", models.UUIDField(unique=True)),
            ("vcpu", models.PositiveIntegerField()),
            ("memory_mb", models.PositiveIntegerField()),
            ("active", models.BooleanField(db_index=True, default=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("stopped_at", models.DateTimeField(blank=True, null=True)),
            ("pool", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reservations", to="training.localtrainingpool")),
        ]),
    ]
