import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('ct', '0001_initial'),
        ('drift', '0004_remove_driftmonitor_reference_asset'),
        ('registry', '0006_require_model_version_reference_snapshot'),
    ]

    operations = [
        migrations.AlterField(
            model_name='driftmonitor',
            name='reference_snapshot',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='drift_monitors',
                to='ct.datasetsnapshot',
            ),
        ),
    ]
