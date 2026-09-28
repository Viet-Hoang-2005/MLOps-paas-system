from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0002_initial"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="modelproject",
            name="project_owner_name_unique",
        ),
        migrations.AddConstraint(
            model_name="modelproject",
            constraint=models.UniqueConstraint(
                condition=Q(is_active=True),
                fields=("owner", "name"),
                name="project_owner_active_name_unique",
            ),
        ),
    ]
