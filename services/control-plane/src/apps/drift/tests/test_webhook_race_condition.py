from unittest.mock import Mock
import json
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject, WorkspaceAsset
from apps.drift.models import DriftMonitor, DriftRun
from apps.drift.tasks import execute_drift_run
from apps.registry.models import ModelVersion


def _drift_fixture():
    owner = get_user_model().objects.create_user("drift-race@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="drift race")
    version = ModelVersion.objects.create(project=project, version="1")
    asset = WorkspaceAsset.objects.create(
        project=project,
        kind="data",
        relative_path="ref.csv",
        s3_uri="s3://bucket/ref.csv",
    )
    monitor = DriftMonitor.objects.create(version=version, reference_asset=asset, name="default")
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
        run.summary_uri = "s3://test-bucket/prefix/summary.json"
        run.save(update_fields=["summary_uri"])

        fake_backend = Mock()
        fake_backend.run.return_value = "logs"

        fake_s3_client = Mock()
        fake_s3_client.get_object.return_value = {
            "Body": Mock(read=lambda: json.dumps({"drift_score": 0.33, "has_drift": False}).encode("utf-8"))
        }
        storage_instance = type("Storage", (), {
            "parse_uri": lambda self, uri: ("test-bucket", "prefix/summary.json"),
            "client": fake_s3_client,
        })()

        from unittest.mock import patch
        with patch("apps.drift.tasks.drift_backend", return_value=fake_backend), \
             patch("apps.drift.tasks.S3Storage", return_value=storage_instance):
            result = execute_drift_run(str(run.public_id))
            self.assertEqual(result, "completed")

        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.drift_score, 0.33)
        self.assertIs(run.has_drift, False)
        self.assertEqual(run.summary["drift_score"], 0.33)
