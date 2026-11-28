import uuid
from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.drift.models import DriftMonitor, DriftRun
from apps.registry.models import ModelArtifact, ModelVersion
from infrastructure.execution.drift import ArgoDriftBackend, DockerDriftBackend


@pytest.mark.django_db
@override_settings(
    CONTROL_PLANE_WEBHOOK_SECRET="test-secret",
    CONTROL_PLANE_INTERNAL_URL="http://control-plane:8000",
)
class TestDriftRunModelPackageURLEndpoint(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user("drift-user@example.com", "password123")
        self.project = ModelProject.objects.create(owner=self.owner, name="test-drift-project")
        self.version = ModelVersion.objects.create(project=self.project, version="1")
        self.monitor = DriftMonitor.objects.create(
            version=self.version,
            reference_uri="s3://bucket/ref.csv",
            name="default-monitor",
        )
        self.package_artifact = ModelArtifact.objects.create(
            version=self.version,
            kind="package",
            name="model-package.zip",
            uri="s3://bucket/artifacts/package/model-package.zip",
            size_bytes=2048,
            checksum="sha256:abc123def456",
        )
        self.run = DriftRun.objects.create(
            monitor=self.monitor,
            status="running",
            idempotency_key="drift-run-pkg-test-1",
        )
        self.client = APIClient()

    def test_get_model_package_url_success(self):
        url = f"/internal/drift-runs/{self.run.public_id}/model-package-url/"
        headers = {
            "HTTP_X_CONTROL_PLANE_SECRET": "test-secret",
            "HTTP_X_TENANT_ID": self.owner.tenant_id,
            "HTTP_X_PROJECT_ID": str(self.project.public_id),
            "HTTP_X_MODEL_VERSION_ID": str(self.version.public_id),
        }
        response = self.client.get(url, **headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn("package_url", response.data)
        self.assertIn("url", response.data)
        self.assertEqual(response.data["size_bytes"], 2048)
        self.assertEqual(response.data["checksum"], "sha256:abc123def456")
        self.assertEqual(response.data["expires_in"], 900)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")

    def test_get_model_package_url_bearer_auth(self):
        url = f"/internal/drift-runs/{self.run.public_id}/model-package-url/"
        headers = {
            "HTTP_AUTHORIZATION": "Bearer test-secret",
            "HTTP_X_TENANT_ID": self.owner.tenant_id,
            "HTTP_X_PROJECT_ID": str(self.project.public_id),
            "HTTP_X_MODEL_VERSION_ID": str(self.version.public_id),
        }
        response = self.client.get(url, **headers)
        self.assertEqual(response.status_code, 200)

    def test_get_model_package_url_rejects_unauthorized(self):
        url = f"/internal/drift-runs/{self.run.public_id}/model-package-url/"
        # Missing secret
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

        # Invalid secret
        response = self.client.get(url, HTTP_X_CONTROL_PLANE_SECRET="wrong-secret")
        self.assertEqual(response.status_code, 403)

    def test_get_model_package_url_rejects_inactive_run(self):
        url = f"/internal/drift-runs/{self.run.public_id}/model-package-url/"
        headers = {
            "HTTP_X_CONTROL_PLANE_SECRET": "test-secret",
            "HTTP_X_TENANT_ID": self.owner.tenant_id,
            "HTTP_X_PROJECT_ID": str(self.project.public_id),
            "HTTP_X_MODEL_VERSION_ID": str(self.version.public_id),
        }
        for terminal_status in ("completed", "failed", "cancelled", "skipped"):
            self.run.status = terminal_status
            self.run.save(update_fields=["status"])
            response = self.client.get(url, **headers)
            self.assertEqual(response.status_code, 404)

        # Active status but stop requested
        self.run.status = "running"
        self.run.execution_stop_requested = True
        self.run.save(update_fields=["status", "execution_stop_requested"])
        response = self.client.get(url, **headers)
        self.assertEqual(response.status_code, 404)

    def test_get_model_package_url_rejects_inactive_project(self):
        self.project.deletion_state = "deleted"
        self.project.save(update_fields=["deletion_state"])
        url = f"/internal/drift-runs/{self.run.public_id}/model-package-url/"
        headers = {
            "HTTP_X_CONTROL_PLANE_SECRET": "test-secret",
            "HTTP_X_TENANT_ID": self.owner.tenant_id,
            "HTTP_X_PROJECT_ID": str(self.project.public_id),
            "HTTP_X_MODEL_VERSION_ID": str(self.version.public_id),
        }
        response = self.client.get(url, **headers)
        self.assertEqual(response.status_code, 404)

    def test_get_model_package_url_rejects_mismatched_identity(self):
        url = f"/internal/drift-runs/{self.run.public_id}/model-package-url/"
        base_headers = {
            "HTTP_X_CONTROL_PLANE_SECRET": "test-secret",
            "HTTP_X_TENANT_ID": self.owner.tenant_id,
            "HTTP_X_PROJECT_ID": str(self.project.public_id),
            "HTTP_X_MODEL_VERSION_ID": str(self.version.public_id),
        }
        # Wrong tenant
        h = {**base_headers, "HTTP_X_TENANT_ID": "other-tenant"}
        self.assertEqual(self.client.get(url, **h).status_code, 404)

        # Wrong project
        h = {**base_headers, "HTTP_X_PROJECT_ID": str(uuid.uuid4())}
        self.assertEqual(self.client.get(url, **h).status_code, 404)

        # Wrong version
        h = {**base_headers, "HTTP_X_MODEL_VERSION_ID": str(uuid.uuid4())}
        self.assertEqual(self.client.get(url, **h).status_code, 404)

    def test_get_model_package_url_returns_404_when_no_package_artifact(self):
        self.package_artifact.delete()
        url = f"/internal/drift-runs/{self.run.public_id}/model-package-url/"
        headers = {
            "HTTP_X_CONTROL_PLANE_SECRET": "test-secret",
            "HTTP_X_TENANT_ID": self.owner.tenant_id,
            "HTTP_X_PROJECT_ID": str(self.project.public_id),
            "HTTP_X_MODEL_VERSION_ID": str(self.version.public_id),
        }
        response = self.client.get(url, **headers)
        self.assertEqual(response.status_code, 404)

    def test_docker_and_argo_payloads_do_not_contain_model_uri_or_package_presigned_url(self):
        from types import SimpleNamespace

        import docker.errors

        # 1. Test Docker Drift payload
        fake_container = SimpleNamespace(id="drift-c-1", attrs={})
        docker_client = SimpleNamespace(
            run=Mock(return_value=fake_container),
            client=SimpleNamespace(containers=SimpleNamespace(get=Mock(side_effect=docker.errors.NotFound("missing")))),
        )
        storage = Mock()
        storage.bucket = "test-bucket"
        storage.presigned_get.return_value = "https://s3/presigned-get"
        storage.presigned_put.return_value = "https://s3/presigned-put"

        docker_backend = DockerDriftBackend(docker_client=docker_client, storage=storage)
        docker_backend.run(self.run)

        call_kwargs = docker_client.run.call_args[1]
        env = call_kwargs["environment"]
        self.assertNotIn("MODEL_URI", env)
        self.assertEqual(env["CONTROL_PLANE_INTERNAL_URL"], "http://control-plane:8000")
        self.assertNotIn("model-package.zip", str(env))
        self.assertNotIn("package_url", str(env))

        # 2. Test Argo Drift payload
        argo_client = Mock()
        argo_client.trigger.return_value = {"accepted": True}
        argo_backend = ArgoDriftBackend(client=argo_client, storage=storage)
        argo_backend.run(self.run)

        url_arg, payload = argo_client.trigger.call_args[0]
        self.assertNotIn("model_uri", payload)
        self.assertEqual(payload["control_plane_internal_url"], "http://control-plane:8000")
        self.assertNotIn("model-package.zip", str(payload))
        self.assertNotIn("package_url", str(payload))
