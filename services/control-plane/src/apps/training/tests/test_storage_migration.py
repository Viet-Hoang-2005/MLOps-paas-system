import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_migration_keeps_original_storage_project_for_existing_jobs():
    old_target = [("training", "0012_trainingjob_owner_workspace")]
    new_target = [("training", "0013_trainingjob_storage_ownership")]
    executor = MigrationExecutor(connection)
    executor.migrate(old_target)
    apps = executor.loader.project_state(old_target).apps
    user = apps.get_model("identity", "CustomUser").objects.create(
        email="storage-migration@example.test", tenant_id="storage-migration"
    )
    project = apps.get_model("catalog", "ModelProject").objects.create(owner_id=user.pk, name="Project")
    workspace = apps.get_model("training", "TrainingWorkspace").objects.create(owner_id=user.pk)
    job = apps.get_model("training", "TrainingJob").objects.create(
        owner_id=user.pk, project_id=project.pk, workspace_id=workspace.pk, model_flavor="sklearn"
    )
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(new_target)
        migrated = (
            executor.loader.project_state(new_target).apps.get_model("training", "TrainingJob").objects.get(pk=job.pk)
        )
        assert migrated.storage_layout == "project"
        assert migrated.storage_project_id == project.public_id
        assert migrated.project_id == project.pk
    finally:
        MigrationExecutor(connection).migrate([("training", "0016_training_build_options")])
