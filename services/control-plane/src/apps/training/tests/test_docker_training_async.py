from types import SimpleNamespace
from unittest.mock import Mock

import docker.errors
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import ModelProject
from apps.training.jobs.storage_scope import expected_training_uris
from apps.training.tests.factories import training_job
from infrastructure.execution.job_containers import labels_for
from infrastructure.execution.training import DockerTrainingBackend


class DockerTrainingAsyncTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user("async-train@example.com", "password123")
        self.project = ModelProject.objects.create(owner=self.owner, name="async-project")
        self.job = training_job(
            project=self.project,
            model_flavor="sklearn",
            status="queued",
            backend="docker",
            vcpu=2,
            memory_mb=4096,
            max_runtime_seconds=3600,
            input_contract="legacy",
            submitted_at=timezone.now(),
        )
        uris = expected_training_uris(self.job, "bucket")
        self.job.code_snapshot_uri = uris["code"]
        self.job.data_snapshot_uri = uris["data"]
        self.job.output_uri = uris["output"]
        self.job.save(update_fields=["code_snapshot_uri", "data_snapshot_uri", "output_uri"])

    def test_docker_training_run_dispatches_without_blocking(self):
        fake_container = SimpleNamespace(id="container-abc-123", attrs={})
        docker_client = SimpleNamespace(
            run=Mock(return_value=fake_container),
            client=SimpleNamespace(containers=SimpleNamespace(get=Mock(side_effect=docker.errors.NotFound("missing")))),
        )
        storage = SimpleNamespace(
            bucket="bucket",
            presigned_get=Mock(return_value="https://s3.test/presigned"),
        )
        backend = DockerTrainingBackend(docker_client=docker_client, storage=storage)

        result = backend.run(self.job)

        self.assertEqual(result, {"dispatched": True, "container_id": "container-abc-123"})
        self.job.refresh_from_db()
        self.assertEqual(self.job.external_job_id, "container-abc-123")
        docker_client.run.assert_called_once()
        call_kwargs = docker_client.run.call_args[1]
        self.assertIn("REDIS_URL", call_kwargs["environment"])
        self.assertEqual(call_kwargs["environment"]["MLFLOW_TRACKING_URI"], "http://control-plane:8000")
        self.assertEqual(call_kwargs["image"], "mlops-paas-training-runner:latest")

    def test_docker_training_poll_running(self):
        container_mock = Mock()
        container_mock.attrs = {"State": {"Status": "running"}}
        docker_client = SimpleNamespace(
            client=SimpleNamespace(containers=SimpleNamespace(get=Mock(return_value=container_mock)))
        )
        backend = DockerTrainingBackend(docker_client=docker_client, storage=SimpleNamespace())

        self.job.external_job_id = "running-container-id"
        container_mock.id = "running-container-id"
        container_mock.attrs["Config"] = {"Labels": labels_for(self.job, "training")}
        result = backend.poll(self.job)

        self.assertEqual(result, {"status": "running", "runtime_id": "running-container-id"})
        container_mock.reload.assert_called_once()
        container_mock.remove.assert_not_called()

    def test_docker_training_poll_completed(self):
        container_mock = Mock()
        container_mock.attrs = {"State": {"Status": "exited", "ExitCode": 0}}
        container_mock.logs.return_value = b"Epoch 10/10 - loss: 0.01\nTraining complete"
        docker_client = SimpleNamespace(
            client=SimpleNamespace(containers=SimpleNamespace(get=Mock(return_value=container_mock)))
        )
        backend = DockerTrainingBackend(docker_client=docker_client, storage=SimpleNamespace())

        self.job.external_job_id = "finished-container-id"
        container_mock.id = "finished-container-id"
        container_mock.attrs["Config"] = {"Labels": labels_for(self.job, "training")}
        result = backend.poll(self.job)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("Training complete", result["logs"])
        container_mock.remove.assert_not_called()

    def test_docker_training_poll_failed(self):
        container_mock = Mock()
        container_mock.attrs = {"State": {"Status": "exited", "ExitCode": 1}}
        container_mock.logs.return_value = b"Traceback (most recent call last):\nValueError: bad data"
        docker_client = SimpleNamespace(
            client=SimpleNamespace(containers=SimpleNamespace(get=Mock(return_value=container_mock)))
        )
        backend = DockerTrainingBackend(docker_client=docker_client, storage=SimpleNamespace())

        self.job.external_job_id = "failed-container-id"
        container_mock.id = "failed-container-id"
        container_mock.attrs["Config"] = {"Labels": labels_for(self.job, "training")}
        result = backend.poll(self.job)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exit_code"], 1)
        self.assertIn("ValueError: bad data", result["error"])
        container_mock.remove.assert_not_called()
