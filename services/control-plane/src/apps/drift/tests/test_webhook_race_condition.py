from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.drift.models import DriftMonitor, DriftRun
from apps.drift.runs.tasks import execute_drift_run
from apps.registry.models import ModelVersion


def _drift_fixture():
    owner = get_user_model().objects.create_user("drift-race@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="drift race")
    version = ModelVersion.objects.create(project=project, version="1")
    monitor = DriftMonitor.objects.create(version=version, reference_uri="s3://bucket/ref.csv", name="default")
    run = DriftRun.objects.create(monitor=monitor, idempotency_key="drift-race-1", status="running")
    return run


@override_settings(CONTROL_PLANE_WEBHOOK_SECRET="test-secret")
class DriftWebhookRaceConditionTests(TestCase):
    def test_webhook_updates_summary_when_celery_completed_first(self):
        run = _drift_fixture()
        # Simulate Celery completing first (without summary)
        run.status = "completed"
        run.save(update_fields=["status"])

        client = APIClient()
        headers = {"HTTP_X_CONTROL_PLANE_SECRET": "test-secret"}
        payload = {
            "drift_summary": {
                "drift_score": 0.42,
                "has_drift": True,
                "dataset_drift": True,
                "share_of_drifted_columns": 0.42,
            }
        }
        response = client.post(f"/internal/webhooks/drift-runs/{run.public_id}/", payload, format="json", **headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"status": "completed"})

        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.drift_score, 0.42)
        self.assertIs(run.has_drift, True)
        self.assertEqual(run.summary["drift_score"], 0.42)

    def test_webhook_returns_duplicate_when_summary_already_recorded(self):
        run = _drift_fixture()
        run.status = "completed"
        run.drift_score = 0.15
        run.has_drift = False
        run.summary = {"drift_score": 0.15, "has_drift": False}
        run.save()

        client = APIClient()
        headers = {"HTTP_X_CONTROL_PLANE_SECRET": "test-secret"}
        payload = {"drift_summary": {"drift_score": 0.15, "has_drift": False}}
        response = client.post(f"/internal/webhooks/drift-runs/{run.public_id}/", payload, format="json", **headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"status": "completed", "duplicate": True})

    def test_webhook_does_not_reactivate_cancelled_run(self):
        run = _drift_fixture()
        run.status = "cancelled"
        run.save(update_fields=["status"])

        client = APIClient()
        headers = {"HTTP_X_CONTROL_PLANE_SECRET": "test-secret"}
        payload = {"drift_summary": {"drift_score": 0.5}}
        response = client.post(f"/internal/webhooks/drift-runs/{run.public_id}/", payload, format="json", **headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"status": "cancelled", "duplicate": True})
        run.refresh_from_db()
        self.assertEqual(run.status, "cancelled")

    def test_execute_drift_run_preserves_webhook_summary_and_handles_s3_fallback(self):
        run = _drift_fixture()
        run.status = "queued"
        run.summary_uri = "s3://test-bucket/prefix/summary.json"
        run.observation_status = "ok"
        run.save(update_fields=["status", "summary_uri", "observation_status"])

        fake_backend = Mock(setting_name="")
        fake_backend.run.return_value = {"dispatched": False}
        fake_backend.poll.side_effect = [{"status": "not_found"}, {"status": "completed", "logs": "logs"}]

        from unittest.mock import patch

        with (
            patch("apps.observability.execution.reconciliation.backend_for", return_value=fake_backend),
            patch(
                "apps.observability.execution.observations._completion_data",
                return_value={"drift_score": 0.33, "has_drift": False},
            ),
        ):
            execute_drift_run(str(run.public_id))
            DriftRun.objects.filter(pk=run.pk).update(next_execution_check_at=timezone.now())
            result = execute_drift_run(str(run.public_id))
            self.assertEqual(result, "completed")

        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.drift_score, 0.33)
        self.assertIs(run.has_drift, False)
        self.assertEqual(run.summary["drift_score"], 0.33)

    def test_webhook_records_skipped_run_without_completion_verification(self):
        run = _drift_fixture()
        client = APIClient()
        headers = {"HTTP_X_CONTROL_PLANE_SECRET": "test-secret"}
        payload = {
            "drift_summary": {
                "status": "skipped",
                "reason": "Insufficient production samples (10 < 100)",
                "samples": 10,
                "minimum_samples": 100,
                "dataset_drift": False,
                "has_drift": False,
            }
        }
        response = client.post(f"/internal/webhooks/drift-runs/{run.public_id}/", payload, format="json", **headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"status": "skipped"})

        run.refresh_from_db()
        self.assertEqual(run.status, "skipped")
        self.assertIsNone(run.drift_score)
        self.assertFalse(run.has_drift)
        self.assertIn("Insufficient production samples", run.error_message)
        self.assertTrue(run.execution_stop_requested)
        self.assertEqual(run.observation_status, "cleanup_pending")

    def test_late_skipped_webhook_does_not_overwrite_completed_result(self):
        run = _drift_fixture()
        run.status = "completed"
        run.drift_score = 0.61
        run.has_drift = True
        run.summary = {"drift_score": 0.61, "has_drift": True}
        run.save(update_fields=["status", "drift_score", "has_drift", "summary"])

        payload = {"drift_summary": {"status": "skipped", "reason": "Insufficient production samples (10 < 100)"}}
        response = APIClient().post(
            f"/internal/webhooks/drift-runs/{run.public_id}/",
            payload,
            format="json",
            HTTP_X_CONTROL_PLANE_SECRET="test-secret",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"status": "completed", "duplicate": True})
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.drift_score, 0.61)
        self.assertIs(run.has_drift, True)
        self.assertEqual(run.summary["drift_score"], 0.61)
        self.assertFalse(run.execution_stop_requested)
