from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
from django.test import TestCase
import docker

from apps.catalog.models import ModelProject
from apps.training.models import TrainingJob
from apps.training.services.storage_scope import expected_training_uris
from apps.training.tasks import execute_training_job, poll_training_job_status
from infrastructure.execution.docker_backends import DockerTrainingBackend


class DockerTrainingAsyncTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user("async-train@example.com", "password123")
        self.project = ModelProject.objects.create(owner=self.owner, name="async-project")
        self.job = TrainingJob.objects.create(
            project=self.project,
            name="async-training-job",
            model_flavor="sklearn",
            status="queued",
            backend="docker",
        )
        uris = expected_training_uris(self.job, "bucket")
        self.job.code_snapshot_uri = uris["code"]
        self.job.data_snapshot_uri = uris["data"]
        self.job.output_uri = uris["output"]
        self.job.save(update_fields=["code_snapshot_uri", "data_snapshot_uri", "output_uri"])

    def test_docker_training_run_dispatches_without_blocking(self):
        fake_container = SimpleNamespace(id="container-abc-123")
        docker_client = SimpleNamespace(
            run=Mock(return_value=fake_container)
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
        self.assertEqual(call_kwargs["image"], "mlops-paas-training-runner:latest")

    def test_docker_training_poll_running(self):
        container_mock = Mock()
        container_mock.attrs = {"State": {"Status": "running"}}
        docker_client = SimpleNamespace(
            client=SimpleNamespace(containers=SimpleNamespace(get=Mock(return_value=container_mock)))
        )
        backend = DockerTrainingBackend(docker_client=docker_client, storage=SimpleNamespace())

        self.job.external_job_id = "running-container-id"
        result = backend.poll(self.job)

        self.assertEqual(result, {"status": "running"})
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
        result = backend.poll(self.job)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("Training complete", result["logs"])
        container_mock.remove.assert_called_once_with(force=True)

    def test_docker_training_poll_failed(self):
        container_mock = Mock()
        container_mock.attrs = {"State": {"Status": "exited", "ExitCode": 1}}
        container_mock.logs.return_value = b"Traceback (most recent call last):\nValueError: bad data"
        docker_client = SimpleNamespace(
            client=SimpleNamespace(containers=SimpleNamespace(get=Mock(return_value=container_mock)))
        )
        backend = DockerTrainingBackend(docker_client=docker_client, storage=SimpleNamespace())

        self.job.external_job_id = "failed-container-id"
        result = backend.poll(self.job)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exit_code"], 1)
        self.assertIn("ValueError: bad data", result["error"])
        container_mock.remove.assert_called_once_with(force=True)

    def test_execute_training_job_dispatches_and_enqueues_poll(self):
        fake_backend = Mock()
        fake_backend.run.return_value = {"dispatched": True, "container_id": "c123"}
        fake_backend.poll = Mock()

        with patch("apps.training.tasks.training_backend", return_value=fake_backend), \
             patch("apps.training.tasks.poll_training_job_status.apply_async") as mock_apply_async:
            status = execute_training_job(str(self.job.public_id))

        self.assertEqual(status, "running")
        mock_apply_async.assert_called_once_with(args=[str(self.job.public_id)], countdown=3)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "running")

    def test_poll_training_job_status_completes_job(self):
        self.job.status = "running"
        self.job.save(update_fields=["status"])

        fake_backend = Mock()
        fake_backend.poll.return_value = {
            "status": "completed",
            "logs": "Training finished successfully",
            "exit_code": 0,
        }

        with patch("apps.training.tasks.training_backend", return_value=fake_backend):
            result = poll_training_job_status(str(self.job.public_id))

        self.assertEqual(result, "completed")
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "completed")
        self.assertTrue(self.job.outputs.filter(relative_path="model.tar.gz").exists())

    def test_poll_training_job_status_fails_job_on_nonzero_exit(self):
        self.job.status = "running"
        self.job.save(update_fields=["status"])

        fake_backend = Mock()
        fake_backend.poll.return_value = {
            "status": "failed",
            "error": "Error in train.py",
            "logs": "Error in train.py",
            "exit_code": 1,
        }

        with patch("apps.training.tasks.training_backend", return_value=fake_backend):
            result = poll_training_job_status(str(self.job.public_id))

        self.assertEqual(result, "failed")
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "failed")
        self.assertIn("Error in train.py", self.job.error_message)
