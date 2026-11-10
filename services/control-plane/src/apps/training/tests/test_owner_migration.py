import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_existing_jobs_keep_owner_during_migration():
    old_target = [("training", "0011_training_workspace")]
    new_target = [("training", "0012_trainingjob_owner_workspace")]
    executor = MigrationExecutor(connection)
    executor.migrate(old_target)
    old_apps = executor.loader.project_state(old_target).apps
    user_model = old_apps.get_model("identity", "CustomUser")
    project_model = old_apps.get_model("catalog", "ModelProject")
    job_model = old_apps.get_model("training", "TrainingJob")
    user = user_model.objects.create(email="migration-owner@example.test", tenant_id="migration-tenant")
    project = project_model.objects.create(owner_id=user.pk, name="Existing")
    job = job_model.objects.create(project_id=project.pk, model_flavor="sklearn")

    try:
        executor = MigrationExecutor(connection)
        executor.migrate(new_target)
        new_apps = executor.loader.project_state(new_target).apps
        migrated = new_apps.get_model("training", "TrainingJob").objects.get(pk=job.pk)
        assert migrated.owner_id == user.pk
        assert migrated.project_id == project.pk
        assert migrated.workspace_id is None
    finally:
        MigrationExecutor(connection).migrate([("training", "0016_training_build_options")])
