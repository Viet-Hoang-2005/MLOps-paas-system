from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject, WorkspaceAsset
from apps.drift.models import DriftMonitor, DriftRun
from apps.drift.tasks import execute_drift_run, handle_drift_detected, poll_drift_run_status
from apps.registry.models import ModelVersion
from infrastructure.execution.docker_backends import DockerDriftBackend


def _create_drift_fixtures():
    owner = get_user_model().objects.create_user("async-drift@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="async-drift-project")
    version = ModelVersion.objects.create(project=project, version="1")
    asset = WorkspaceAsset.objects.create(
        project=project,
        kind="data",
        relative_path="reference.csv",
        s3_uri="s3://bucket/reference.csv",
    )
    monitor = DriftMonitor.objects.create(
        version=version,
        reference_asset=asset,
        name="async-monitor",
        backend="docker",
    )
    run = DriftRun.objects.create(
        monitor=monitor,
        idempotency_key="async-run-1",
        status="queued",
    )
    return owner, project, version, monitor, run


class DockerDriftAsyncTests(TestCase):
    def setUp(self):
        self.owner, self.project, self.version, self.monitor, self.drift_run = _create_drift_fixtures()

    def test_docker_drift_run_dispatches_without_blocking(self):
        fake_container = SimpleNamespace(id="drift-container-123")
        docker_client = SimpleNamespace(
            run=Mock(return_value=fake_container)
        )
        storage = SimpleNamespace(
            bucket="bucket",
            presigned_get=Mock(return_value="https://s3.test/presigned-get"),
            presigned_put=Mock(return_value="https://s3.test/presigned-put"),
        )
        backend = DockerDriftBackend(docker_client=docker_client, storage=storage)

        result = backend.run(self.drift_run)

        self.assertEqual(result, {"dispatched": True, "container_id": "drift-container-123"})
        self.drift_run.refresh_from_db()
        self.assertEqual(self.drift_run.external_run_id, "drift-container-123")
        docker_client.run.assert_called_once()
        call_kwargs = docker_client.run.call_args[1]
        self.assertEqual(call_kwargs["image"], "mlops-paas-evidently")
        self.assertEqual(call_kwargs["name"], f"drift-{self.drift_run.public_id}")

    def test_docker_drift_poll_running(self):
        container_mock = Mock()
        container_mock.attrs = {"State": {"Status": "running"}}
        docker_client = SimpleNamespace(
            client=SimpleNamespace(containers=SimpleNamespace(get=Mock(return_value=container_mock)))
        )
        backend = DockerDriftBackend(docker_client=docker_client, storage=SimpleNamespace())

        self.drift_run.external_run_id = "running-drift-id"
        result = backend.poll(self.drift_run)

        self.assertEqual(result, {"status": "running"})
        container_mock.reload.assert_called_once()
        container_mock.remove.assert_not_called()

    def test_docker_drift_poll_completed(self):
        container_mock = Mock()
        container_mock.attrs = {"State": {"Status": "exited", "ExitCode": 0}}
        container_mock.logs.return_value = b"Drift report generated successfully."
        docker_client = SimpleNamespace(
            client=SimpleNamespace(containers=SimpleNamespace(get=Mock(return_value=container_mock)))
        )
        backend = DockerDriftBackend(docker_client=docker_client, storage=SimpleNamespace())

        self.drift_run.external_run_id = "completed-drift-id"
        result = backend.poll(self.drift_run)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["exit_code"], 0)
        container_mock.remove.assert_called_once_with(force=True)

    def test_docker_drift_poll_failed(self):
        container_mock = Mock()
        container_mock.attrs = {"State": {"Status": "exited", "ExitCode": 1}}
        container_mock.logs.return_value = b"ValueError: Missing required feature columns"
        docker_client = SimpleNamespace(
            client=SimpleNamespace(containers=SimpleNamespace(get=Mock(return_value=container_mock)))
        )
        backend = DockerDriftBackend(docker_client=docker_client, storage=SimpleNamespace())

        self.drift_run.external_run_id = "failed-drift-id"
        result = backend.poll(self.drift_run)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exit_code"], 1)
        self.assertIn("Missing required feature columns", result["error"])
        container_mock.remove.assert_called_once_with(force=True)

    def test_execute_drift_run_dispatches_and_schedules_poll(self):
        fake_backend = Mock()
        fake_backend.run.return_value = {"dispatched": True, "container_id": "c123"}
        fake_backend.poll = Mock()

        with patch("apps.drift.tasks.drift_backend", return_value=fake_backend), \
             patch("apps.drift.tasks.poll_drift_run_status.apply_async") as mock_apply_async:
            status = execute_drift_run(str(self.drift_run.public_id))

        self.assertEqual(status, "running")
        mock_apply_async.assert_called_once_with(args=[str(self.drift_run.public_id)], countdown=5)
        self.drift_run.refresh_from_db()
        self.assertEqual(self.drift_run.status, "running")

    def test_poll_drift_run_status_completes_and_triggers_ct_hook(self):
        self.drift_run.status = "running"
        self.drift_run.summary = {"drift_score": 0.35, "has_drift": True}
        self.drift_run.drift_score = 0.35
        self.drift_run.has_drift = True
        self.drift_run.save(update_fields=["status", "summary", "drift_score", "has_drift"])

        fake_backend = Mock()
        fake_backend.poll.return_value = {"status": "completed", "logs": "Done", "exit_code": 0}

        with patch("apps.drift.tasks.drift_backend", return_value=fake_backend), \
             patch("apps.drift.tasks.handle_drift_detected.delay") as mock_ct_delay, \
             self.captureOnCommitCallbacks(execute=True):
            result = poll_drift_run_status(str(self.drift_run.public_id))

        self.assertEqual(result, "completed")
        self.drift_run.refresh_from_db()
        self.assertEqual(self.drift_run.status, "completed")
        mock_ct_delay.assert_called_once_with(str(self.drift_run.public_id))

    def test_handle_drift_detected_prepares_evidence_payload(self):
        self.drift_run.status = "completed"
        self.drift_run.drift_score = 0.45
        self.drift_run.has_drift = True
        self.drift_run.summary = {
            "drift_score": 0.45,
            "has_drift": True,
            "drifted_features": ["age", "income"],
        }
        self.drift_run.save(update_fields=["status", "drift_score", "has_drift", "summary"])

        result = handle_drift_detected(str(self.drift_run.public_id))

        self.assertEqual(result["status"], "drift_handled")
        self.assertEqual(result["model_version_id"], str(self.version.public_id))
        self.assertEqual(result["drift_score"], 0.45)
        self.assertIn("drifted_features", result["evidence"]["summary"])


@override_settings(CONTROL_PLANE_WEBHOOK_SECRET="test-secret")
class DriftWebhookContinuousTrainingHookTests(TestCase):
    def setUp(self):
        self.owner, self.project, self.version, self.monitor, self.drift_run = _create_drift_fixtures()
        self.client = APIClient()
        self.headers = {"HTTP_X_CONTROL_PLANE_SECRET": "test-secret"}

    def test_webhook_triggers_ct_hook_when_drift_detected(self):
        payload = {
            "drift_summary": {
                "drift_score": 0.55,
                "has_drift": True,
                "dataset_drift": True,
                "share_of_drifted_columns": 0.55,
            }
        }
        with patch("apps.drift.tasks.handle_drift_detected.delay") as mock_ct_delay, \
             self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"/internal/webhooks/drift-runs/{self.drift_run.public_id}/",
                payload,
                format="json",
                **self.headers,
            )

        self.assertEqual(response.status_code, 200)
        self.drift_run.refresh_from_db()
        self.assertTrue(self.drift_run.has_drift)
        mock_ct_delay.assert_called_once_with(str(self.drift_run.public_id))

    def test_webhook_does_not_trigger_ct_hook_when_no_drift(self):
        payload = {
            "drift_summary": {
                "drift_score": 0.05,
                "has_drift": False,
                "dataset_drift": False,
                "share_of_drifted_columns": 0.05,
            }
        }
        with patch("apps.drift.tasks.handle_drift_detected.delay") as mock_ct_delay:
            response = self.client.post(
                f"/internal/webhooks/drift-runs/{self.drift_run.public_id}/",
                payload,
                format="json",
                **self.headers,
            )

        self.assertEqual(response.status_code, 200)
        self.drift_run.refresh_from_db()
        self.assertFalse(self.drift_run.has_drift)
        mock_ct_delay.assert_not_called()
