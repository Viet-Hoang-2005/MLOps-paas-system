from types import SimpleNamespace
from unittest.mock import Mock
import docker.errors
import pytest
from django.contrib.auth import get_user_model
from apps.training.models import TrainingJob
from apps.training.services.storage_scope import expected_training_uris
from infrastructure.execution.docker_backends import DockerTrainingBackend
from infrastructure.execution.job_containers import labels_for
from infrastructure.execution import workspace_docker


@pytest.mark.django_db
def test_preparation_is_async_and_main_container_mounts_only_job_input_read_only():
    user = get_user_model().objects.create_user("docker-workspace@example.test", "password")
    job = TrainingJob.objects.create(owner=user, storage_layout="tenant", input_contract="workspace", backend="docker", status="queued", model_flavor="sklearn")
    uris = expected_training_uris(job, "bucket")
    job.code_snapshot_uri, job.data_snapshot_uri, job.output_uri = uris["code"], uris["data"], uris["output"]
    job.save()
    containers, volumes = {}, {}
    def get_container(name):
        if name not in containers:
            raise docker.errors.NotFound("missing")
        return containers[name]
    def get_volume(name):
        if name not in volumes:
            raise docker.errors.NotFound("missing")
        return volumes[name]
    def volume_create(**kwargs):
        volume = SimpleNamespace(attrs={"Labels": kwargs["labels"]}, reload=Mock(), remove=Mock())
        volumes[kwargs["name"]] = volume
        return volume
    helper_run = Mock()
    def create_helper(image, **kwargs):
        helper_run(image, **kwargs)
        helper = SimpleNamespace(attrs={"Config": {"Labels": kwargs["labels"]}, "State": {"Status": "running"}}, reload=Mock(), remove=Mock())
        containers[kwargs["name"]] = helper
        return helper
    client = SimpleNamespace(containers=SimpleNamespace(get=get_container, run=create_helper),
        volumes=SimpleNamespace(get=get_volume, create=volume_create), images=SimpleNamespace(get=Mock()))
    main = SimpleNamespace(id="main-runtime", attrs={"State": {"Status": "running"}}, reload=Mock())
    docker_client = SimpleNamespace(client=client, run=Mock(return_value=main))
    storage = SimpleNamespace(bucket="bucket", presigned_get=lambda *args: "https://example.test/input")
    backend = DockerTrainingBackend(docker_client=docker_client, storage=storage)

    assert backend.run(job)["preparing"] is True
    docker_client.run.assert_not_called()
    helper = containers[workspace_docker.names(job)[0]]
    assert backend.poll(job)["status"] == "preparing"
    helper.attrs["State"] = {"Status": "exited", "ExitCode": 0}
    assert backend.poll(job)["status"] == "created"
    backend.run(job)
    options = docker_client.run.call_args.kwargs
    assert options["volumes"] == {workspace_docker.names(job)[1]: {"bind": "/prepared", "mode": "ro"}}
    assert options["cap_drop"] == ["ALL"]
    assert options["environment"]["INPUT_CONTRACT"] == "workspace"
    assert "S3_INPUT_DOWNLOAD_CAPABILITY" not in options["environment"]
    assert "RUNTIME_CONFIG_CAPABILITY" in options["environment"]
    assert "AWS_ACCESS_KEY_ID" not in options["environment"]
    assert helper_run.call_args.kwargs["user"] == "0:0"
    assert helper_run.call_args.kwargs["cap_drop"] == ["ALL"]
    assert labels_for(job, "training")["mlops_project_id"] == ""


@pytest.mark.django_db
def test_input_cleanup_refuses_foreign_volume():
    from common.api.exceptions import Conflict
    user = get_user_model().objects.create_user("volume-owner@example.test", "password")
    job = TrainingJob.objects.create(owner=user, model_flavor="sklearn", storage_layout="tenant")
    volume = SimpleNamespace(attrs={"Labels": {"mlops_role": "input"}}, reload=Mock(), remove=Mock())
    client = SimpleNamespace(containers=SimpleNamespace(get=Mock(side_effect=docker.errors.NotFound("missing"))),
        volumes=SimpleNamespace(get=lambda name: volume))
    with pytest.raises(Conflict):
        workspace_docker.cleanup(client, job)
    volume.remove.assert_not_called()
