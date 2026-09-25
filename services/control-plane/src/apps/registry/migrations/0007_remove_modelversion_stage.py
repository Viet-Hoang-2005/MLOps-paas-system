from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("registry", "0006_require_model_version_reference_snapshot")]

    operations = [migrations.RemoveField(model_name="modelversion", name="stage")]
