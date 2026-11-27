from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("registry", "0003_modelversion_deletion_requested")]

    operations = [
        migrations.AddField(
            model_name="modelversion",
            name="deletion_cleanup_due_at",
            field=models.DateTimeField(blank=True, db_index=True, editable=False, null=True),
        ),
    ]
