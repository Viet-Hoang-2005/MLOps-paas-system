from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("identity", "0002_customuser_purge_started_at")]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="purge_next_attempt_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
