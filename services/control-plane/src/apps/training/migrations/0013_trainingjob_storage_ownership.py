from django.db import migrations, models
from django.db.models import OuterRef, Subquery
import django.db.models.deletion


def preserve_storage_project(apps, schema_editor):
    jobs = apps.get_model("training", "TrainingJob")
    projects = apps.get_model("catalog", "ModelProject")
    public_id = projects.objects.filter(pk=OuterRef("project_id")).values("public_id")[:1]
    jobs.objects.using(schema_editor.connection.alias).filter(project__isnull=False).update(storage_project_id=Subquery(public_id))


class Migration(migrations.Migration):
    dependencies = [("training", "0012_trainingjob_owner_workspace")]

    operations = [
        migrations.AddField(model_name="trainingjob", name="storage_project_id",
                            field=models.UUIDField(blank=True, null=True, editable=False)),
        migrations.AddField(model_name="trainingjob", name="storage_layout",
                            field=models.CharField(choices=[("project", "Project"), ("tenant", "Tenant")],
                                                   default="project", max_length=16)),
        migrations.RunPython(preserve_storage_project, migrations.RunPython.noop),
        migrations.AlterField(model_name="trainingjob", name="project",
                              field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                      related_name="training_jobs", to="catalog.modelproject")),
    ]
