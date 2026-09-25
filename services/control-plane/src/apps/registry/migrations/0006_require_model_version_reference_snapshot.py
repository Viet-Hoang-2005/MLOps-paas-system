import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("registry", "0005_alter_modelartifact_kind")]

    operations = [
        migrations.AlterField(
            model_name="modelversion",
            name="reference_snapshot",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="model_versions", to="ct.datasetsnapshot"),
        ),
    ]
