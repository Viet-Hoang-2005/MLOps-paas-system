import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("deployment", "0004_remove_build_registered_version_and_more")]

    operations = [
        migrations.AlterField(
            model_name="deployment",
            name="project",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="deployments", to="catalog.modelproject"),
        ),
        migrations.AlterField(
            model_name="deployment",
            name="target",
            field=models.CharField(choices=[("staging", "Staging"), ("production", "Production")], max_length=20),
        ),
    ]
