from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, BuildInputAsset
from infrastructure.storage.s3 import StoredObject


class FakeStorage:
    def __init__(self, bucket="test-bucket"):
        self.bucket = bucket
        self.client = SimpleNamespace(
            generate_presigned_url=Mock(return_value="https://s3.test/presigned-put-url"),
            head_object=Mock(return_value={"ContentLength": 1024, "ContentType": "application/octet-stream", "Metadata": {"sha256": "fake-hash"}}),
        )

    def presigned_put(self, uri, expires_in=900, content_type=None):
        return f"https://s3.test/presigned-put-url?uri={uri}&expires={expires_in}"

    def parse_uri(self, uri):
        if not uri.startswith("s3://"):
            raise ValueError("Expected an s3:// URI")
        bucket, key = uri[5:].split("/", 1)
        return bucket, key

    def delete_prefix(self, prefix):
        pass


class PresignedBuildUploadTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user("presigned-owner@example.com", "password123")
        self.other_user = get_user_model().objects.create_user("presigned-other@example.com", "password123")
        self.project = ModelProject.objects.create(owner=self.owner, name="Presigned ML Project")
        self.client = APIClient()

    def test_presigned_upload_url_success(self):
        self.client.force_authenticate(self.owner)
        payload = {
            "flavor": "sklearn",
            "artifact_format": "raw",
            "filename": "model.joblib",
            "content_type": "application/octet-stream",
        }
        response = self.client.post(
            f"/api/models/{self.project.public_id}/builds/upload-url/",
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertIn("upload_url", data)
        self.assertIn("s3_uri", data)
        self.assertIn("draft_build_id", data)
        self.assertEqual(data["filename"], "model.joblib")

        expected_prefix = f"users/{self.owner.tenant_id}/models/{self.project.public_id}/builds/{data['draft_build_id']}/inputs/source_artifact/model.joblib"
        self.assertTrue(data["s3_uri"].endswith(expected_prefix))

    def test_presigned_upload_url_rejects_incompatible_extension(self):
        self.client.force_authenticate(self.owner)
        payload = {
            "flavor": "sklearn",
            "artifact_format": "raw",
            "filename": "model.h5",  # .h5 is tensorflow, not sklearn
        }
        response = self.client.post(
            f"/api/models/{self.project.public_id}/builds/upload-url/",
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        detail = response.data.get("error", {}).get("detail", response.data)
        self.assertIn("source_artifact", detail)

    def test_presigned_upload_url_other_user_forbidden(self):
        self.client.force_authenticate(self.other_user)
        payload = {
            "flavor": "sklearn",
            "artifact_format": "raw",
            "filename": "model.joblib",
        }
        response = self.client.post(
            f"/api/models/{self.project.public_id}/builds/upload-url/",
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_manual_build_with_direct_s3_uri_success(self):
        self.client.force_authenticate(self.owner)
        fake_storage = FakeStorage()

        draft_id = "11111111-2222-3333-4444-555555555555"
        key = f"users/{self.owner.tenant_id}/models/{self.project.public_id}/builds/{draft_id}/inputs/source_artifact/model.pkl"
        s3_uri = f"s3://test-bucket/{key}"

        payload = {
            "flavor": "sklearn",
            "artifact_format": "raw",
            "requirements_text": "scikit-learn==1.3.0",
            "source_artifact_uri": s3_uri,
            "source_artifact_name": "model.pkl",
            "source_artifact_size": 2048,
        }

        with patch("apps.deployment.services.builds.S3Storage", return_value=fake_storage), \
             patch("apps.deployment.services.builds.execute_build.delay", return_value=SimpleNamespace(id="task-123")), \
             self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"/api/models/{self.project.public_id}/builds/",
                payload,
                format="json",
            )

        self.assertEqual(response.status_code, 201)
        build_id = response.data["id"]
        build = Build.objects.get(public_id=build_id)
        self.assertEqual(build.status, "queued")
        self.assertEqual(build.flavor, "sklearn")

        asset = build.input_assets.filter(kind="source_artifact").first()
        self.assertIsNotNone(asset)
        self.assertEqual(asset.name, "model.pkl")
        self.assertEqual(asset.s3_uri, s3_uri)

    def test_manual_build_rejects_cross_tenant_s3_uri(self):
        self.client.force_authenticate(self.owner)
        fake_storage = FakeStorage()

        # Malicious URI pointing to another tenant's path
        malicious_uri = "s3://test-bucket/users/other-tenant/models/other-proj/builds/abc/inputs/source_artifact/model.pkl"
        payload = {
            "flavor": "sklearn",
            "artifact_format": "raw",
            "source_artifact_uri": malicious_uri,
        }

        with patch("apps.deployment.services.builds.S3Storage", return_value=fake_storage):
            response = self.client.post(
                f"/api/models/{self.project.public_id}/builds/",
                payload,
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        detail = response.data.get("error", {}).get("detail", response.data)
        self.assertIn("source_artifact_uri", detail)
