import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("training", "0010_local_training_reservations"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(name="TrainingWorkspace", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
            ("entry_point", models.CharField(blank=True, max_length=512)),
            ("environment", models.JSONField(blank=True, default=dict)),
            ("revision", models.PositiveIntegerField(default=1)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="training_workspaces", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="TrainingWorkspaceEntry", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
            ("relative_path", models.CharField(max_length=512)),
            ("kind", models.CharField(choices=[("folder", "Folder"), ("script", "Script"), ("data", "Data"), ("config", "Config"), ("document", "Document"), ("requirements", "Requirements")], max_length=16)),
            ("s3_uri", models.CharField(blank=True, max_length=1024)),
            ("checksum", models.CharField(blank=True, max_length=64)),
            ("size_bytes", models.PositiveBigIntegerField(default=0)),
            ("content_type", models.CharField(blank=True, max_length=160)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entries", to="training.trainingworkspace")),
        ]),
        migrations.CreateModel(name="TrainingWorkspaceSecret", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("name", models.CharField(max_length=128)),
            ("ciphertext", models.BinaryField()),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="secrets", to="training.trainingworkspace")),
        ]),
        migrations.AddConstraint(model_name="trainingworkspaceentry", constraint=models.UniqueConstraint(fields=("workspace", "relative_path"), name="training_workspace_entry_path_unique")),
        migrations.AddConstraint(model_name="trainingworkspacesecret", constraint=models.UniqueConstraint(fields=("workspace", "name"), name="training_workspace_secret_unique")),
    ]
