from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("identity", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="purge_started_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddConstraint(
            model_name="customuser",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(purge_started_at__isnull=True) | models.Q(is_active=False, deleted_at__isnull=False)
                ),
                name="identity_user_purge_requires_inactive",
            ),
        ),
    ]
