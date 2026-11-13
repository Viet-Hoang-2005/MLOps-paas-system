from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("deployment", "0002_initial")]
    operations = [migrations.AlterField(
        model_name="deployment", name="status",
        field=models.CharField(default="pending", max_length=30, choices=[
            (value, value.replace("_", " ").title())
            for value in ("pending", "deploying", "healthy", "unhealthy", "failed", "stopped", "unconfirmed")
        ]),
    )]
