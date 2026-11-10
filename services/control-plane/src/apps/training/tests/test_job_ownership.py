import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.catalog.models import ModelProject
from apps.training.models import TrainingJob, TrainingWorkspace
from apps.training.selectors import jobs_for_user


@pytest.mark.django_db
def test_legacy_job_records_owner_and_is_scoped_to_owner():
    user = get_user_model().objects.create_user("training-owner@example.test", "test-password")
    other = get_user_model().objects.create_user("training-other@example.test", "test-password")
    project = ModelProject.objects.create(owner=user, name="Project")
    job = TrainingJob.objects.create(project=project, model_flavor="sklearn")

    assert job.owner_id == user.pk
    assert list(jobs_for_user(user)) == [job]
    assert not jobs_for_user(other).exists()


@pytest.mark.django_db
def test_rejects_job_owner_inconsistent_with_project_or_workspace():
    user = get_user_model().objects.create_user("training-owner@example.test", "test-password")
    other = get_user_model().objects.create_user("training-other@example.test", "test-password")
    project = ModelProject.objects.create(owner=user, name="Project")
    workspace = TrainingWorkspace.objects.create(owner=other)

    with pytest.raises(ValidationError, match="project must have the same owner"):
        TrainingJob.objects.create(project=project, owner=other, model_flavor="sklearn")
    with pytest.raises(ValidationError, match="workspace must have the same owner"):
        TrainingJob.objects.create(project=project, workspace=workspace, model_flavor="sklearn")


@pytest.mark.django_db
def test_unassigned_job_tracking_is_tenant_and_capability_scoped():
    from types import SimpleNamespace
    from apps.mlflow.auth import authenticate_mlflow_request, _resolve_target_job
    from apps.training.services.capabilities import issue_capability

    owner = get_user_model().objects.create_user("tracking-owner@example.test", "test-password")
    other = get_user_model().objects.create_user("tracking-other@example.test", "test-password")
    job = TrainingJob.objects.create(owner=owner, model_flavor="sklearn", status="running", storage_layout="tenant")
    token = issue_capability(job, "tracking")
    request = SimpleNamespace(headers={"Authorization": f"Bearer {token}"}, user=None)
    authed_job, project, user, tenant, _ = authenticate_mlflow_request(request)
    assert authed_job == job
    assert project is None
    assert user == owner
    assert _resolve_target_job(job, str(job.public_id), tenant, for_mutation=True) == (job, None)
    assert _resolve_target_job(None, str(job.public_id), other.tenant_id)[1].status_code == 404
