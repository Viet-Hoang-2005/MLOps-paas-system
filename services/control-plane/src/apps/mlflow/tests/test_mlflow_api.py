import hashlib
from unittest.mock import patch
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.access.models import UserAPIKey
from apps.catalog.models import ModelProject
from apps.training.models import (
    TrainingJob,
    TrainingJobCapability,
    TrainingJobMetric,
    TrainingJobParam,
    TrainingJobTag,
    TrainingOutput,
)
from apps.training.services.capabilities import issue_capability
from apps.training.services.jobs import cancel_job
from infrastructure.storage.s3 import StoredObject


class MockS3Storage:
    def __init__(self):
        self.bucket = "mlops-paas-artifacts"
        self.objects = {}

    def put(self, key, body, content_type="application/octet-stream"):
        payload = body.read() if hasattr(body, "read") else body
        if isinstance(payload, str):
            payload = payload.encode()
        uri = f"s3://{self.bucket}/{key}"
        self.objects[uri] = payload
        checksum = hashlib.sha256(payload).hexdigest()
        return StoredObject(key, uri, checksum, len(payload), content_type)

    def upload_fileobj(self, fileobj, key, content_type="application/octet-stream", checksum=None, size_bytes=None):
        payload = fileobj.read() if hasattr(fileobj, "read") else fileobj
        if isinstance(payload, str):
            payload = payload.encode()
        uri = f"s3://{self.bucket}/{key}"
        self.objects[uri] = payload
        actual_checksum = checksum or hashlib.sha256(payload).hexdigest()
        actual_size = size_bytes if size_bytes is not None else len(payload)
        return StoredObject(key, uri, actual_checksum, actual_size, content_type)

    def head(self, uri: str):
        if uri not in self.objects:
            raise FileNotFoundError(f"Key not found: {uri}")
        payload = self.objects[uri]
        checksum = hashlib.sha256(payload).hexdigest()
        key = uri.split(f"s3://{self.bucket}/", 1)[-1] if f"s3://{self.bucket}/" in uri else uri
        return StoredObject(
            key=key,
            uri=uri,
            checksum=checksum,
            size_bytes=len(payload),
            content_type="application/octet-stream",
        )

    def open_stream(self, uri: str):
        if uri not in self.objects:
            raise FileNotFoundError(f"Key not found: {uri}")
        payload = self.objects[uri]
        import io
        return io.BytesIO(payload), len(payload), "application/octet-stream"

    def read(self, uri, max_bytes=500 * 1024 * 1024):
        if uri not in self.objects:
            raise FileNotFoundError(f"Key not found: {uri}")
        val = self.objects[uri]
        if len(val) > max_bytes:
            raise ValueError("Object exceeds max bytes")
        return val

    def delete(self, uri):
        self.objects.pop(uri, None)

    def delete_prefix(self, prefix):
        for k in list(self.objects.keys()):
            if prefix in k:
                self.objects.pop(k, None)

    def presigned_get(self, uri, expires_in=900):
        return f"https://s3.mock.download/{uri}"

    def presigned_put(self, uri, expires_in=900, content_type=None, size_bytes=None):
        return f"https://s3.mock.upload/{uri}"


class MLflowCompatibilityTests(APITestCase):
    def setUp(self):
        self.mock_storage = MockS3Storage()
        self.storage_patcher = patch("apps.mlflow.views.artifacts.S3Storage", lambda: self.mock_storage)
        self.storage_patcher.start()
        self.addCleanup(self.storage_patcher.stop)

        User = get_user_model()
        self.user = User.objects.create_user(
            email="tester@example.com",
            password="password123",
            tenant_id="tenant-1234",
        )
        self.project = ModelProject.objects.create(
            owner=self.user,
            name="iris-classification",
        )
        self.job = TrainingJob.objects.create(
            project=self.project,
            name="job-run-1",
            model_flavor="sklearn",
            status="running",
        )
        self.token = issue_capability(self.job, "tracking")

    def test_mlflow_unauthenticated_rejected(self):
        response = self.client.post("/api/2.0/mlflow/runs/create", data={}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error_code"], "UNAUTHENTICATED")

    def test_mlflow_runs_create_with_capability_token(self):
        response = self.client.post(
            "/api/2.0/mlflow/runs/create",
            data={"run_name": "custom-run", "tags": [{"key": "framework", "value": "pytorch"}]},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertEqual(data["run"]["info"]["run_id"], str(self.job.public_id))
        self.assertEqual(data["run"]["info"]["experiment_id"], str(self.job.project.public_id))
        self.assertTrue(TrainingJobTag.objects.filter(job=self.job, name="framework", value="pytorch").exists())

    def test_mlflow_runs_log_batch(self):
        payload = {
            "run_id": str(self.job.public_id),
            "metrics": [
                {"key": "loss", "value": 0.5, "step": 1, "timestamp": 1700000000000},
                {"key": "loss", "value": 0.25, "step": 2, "timestamp": 1700000001000},
                {"key": "accuracy", "value": 0.95, "step": 2, "timestamp": 1700000001000},
            ],
            "params": [
                {"key": "learning_rate", "value": "0.001"},
                {"key": "batch_size", "value": "32"},
            ],
            "tags": [
                {"key": "optimizer", "value": "adam"},
            ],
        }

        response = self.client.post(
            "/api/2.0/mlflow/runs/log-batch",
            data=payload,
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify metrics saved to DB
        self.assertEqual(TrainingJobMetric.objects.filter(job=self.job, name="loss").count(), 2)
        self.assertTrue(TrainingJobMetric.objects.filter(job=self.job, name="accuracy", value=0.95).exists())

        # Verify params saved
        self.assertTrue(TrainingJobParam.objects.filter(job=self.job, name="learning_rate", value="0.001").exists())
        self.assertTrue(TrainingJobParam.objects.filter(job=self.job, name="batch_size", value="32").exists())

        # Verify job.tracking summary updated
        self.job.refresh_from_db()
        self.assertEqual(self.job.tracking["metrics"]["loss"], 0.25)
        self.assertEqual(self.job.tracking["metrics"]["accuracy"], 0.95)
        self.assertEqual(self.job.tracking["params"]["learning_rate"], "0.001")

    def test_mlflow_tenant_isolation(self):
        """Ensure a token from Tenant A cannot log or read runs of Tenant B."""
        User = get_user_model()
        other_user = User.objects.create_user(
            email="other@example.com",
            password="password123",
            tenant_id="tenant-9999",
        )
        other_project = ModelProject.objects.create(
            owner=other_user,
            name="secret-project",
        )
        other_job = TrainingJob.objects.create(
            project=other_project,
            name="secret-job",
            model_flavor="sklearn",
            status="running",
        )

        # Try logging to other_job using self.token (tenant-1234)
        response = self.client.post(
            "/api/2.0/mlflow/runs/log-metric",
            data={"run_id": str(other_job.public_id), "key": "hacked", "value": 1.0, "step": 1},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error_code"], "RESOURCE_DOES_NOT_EXIST")
        self.assertFalse(TrainingJobMetric.objects.filter(name="hacked").exists())

    def test_mlflow_metrics_history_query(self):
        self.client.post(
            "/api/2.0/mlflow/runs/log-metric",
            data={"run_id": str(self.job.public_id), "key": "val_loss", "value": 0.42, "step": 1},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        # Web query endpoint (authenticated as project owner)
        self.client.force_authenticate(user=self.user)
        history_resp = self.client.get(f"/api/training-jobs/{self.job.public_id}/metrics-history/")
        self.assertEqual(history_resp.status_code, status.HTTP_200_OK)
        data = history_resp.data
        self.assertEqual(len(data["series"]), 1)
        self.assertEqual(data["series"][0]["name"], "val_loss")
        self.assertEqual(data["series"][0]["points"][0]["value"], 0.42)

    def test_mlflow_runs_create_with_api_key_disabled(self):
        """
        Verify that creating MLflow runs via API key is disabled to prevent orphan TrainingJobs.
        API keys can still query existing runs, experiments, and metrics.
        """
        raw_key, prefix, key_hash = UserAPIKey.issue()
        UserAPIKey.objects.create(
            user=self.user,
            name="ci-key",
            key_prefix=prefix,
            key_hash=key_hash,
        )

        initial_job_count = TrainingJob.objects.count()

        # 1. Attempting to create run via API key must return 403 PERMISSION_DENIED
        response = self.client.post(
            "/api/2.0/mlflow/runs/create",
            data={"run_name": "external-run-from-laptop"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["error_code"], "PERMISSION_DENIED")
        self.assertIn("Creating MLflow runs via API key is disabled", response.data["message"])

        # No orphan TrainingJob was created in the database
        self.assertEqual(TrainingJob.objects.count(), initial_job_count)

        # 2. But API key can still authenticate and query existing runs/experiments
        get_resp = self.client.get(
            f"/api/2.0/mlflow/runs/get?run_id={self.job.public_id}",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(get_resp.data["run"]["info"]["run_id"], str(self.job.public_id))

    def test_training_jobs_compare_endpoint(self):
        job2 = TrainingJob.objects.create(
            project=self.project,
            name="job-run-2",
            model_flavor="sklearn",
            status="completed",
        )
        TrainingJobMetric.objects.create(job=self.job, name="accuracy", value=0.91, step=1)
        TrainingJobMetric.objects.create(job=job2, name="accuracy", value=0.96, step=1)
        TrainingJobParam.objects.create(job=self.job, name="lr", value="0.01")
        TrainingJobParam.objects.create(job=job2, name="lr", value="0.001")

        self.client.force_authenticate(user=self.user)
        resp = self.client.get(f"/api/training-jobs/compare/?job_ids={self.job.public_id},{job2.public_id}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data
        self.assertEqual(len(data["runs"]), 2)
        self.assertIn("accuracy", data["metric_names"])
        self.assertIn("lr", data["param_names"])

    def test_mlflow_runs_create_and_get_returns_mlflow_artifacts_uri(self):
        # 1. runs/create
        create_resp = self.client.post(
            "/api/2.0/mlflow/runs/create",
            data={"run_name": "artifact-uri-test"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_200_OK)
        expected_prefix = (
            f"mlflow-artifacts:/users/{self.user.tenant_id}/models/{self.project.public_id}/"
            "training/jobs/"
        )
        self.assertTrue(create_resp.data["run"]["info"]["artifact_uri"].startswith(expected_prefix))

        # 2. runs/get
        get_resp = self.client.get(
            f"/api/2.0/mlflow/runs/get?run_id={self.job.public_id}",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)
        expected_uri = (
            f"mlflow-artifacts:/users/{self.user.tenant_id}/models/{self.project.public_id}/"
            f"training/jobs/{self.job.public_id}/mlflow/artifacts"
        )
        self.assertEqual(get_resp.data["run"]["info"]["artifact_uri"], expected_uri)

    def test_mlflow_artifact_proxy_upload_and_download(self):
        file_content = b"pickle-serialized-model-bytes-123456789"
        upload_path = (
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/users/{self.user.tenant_id}/models/"
            f"{self.project.public_id}/training/jobs/{self.job.public_id}/mlflow/artifacts/model/model.pkl"
        )

        # 1. PUT upload
        put_resp = self.client.put(
            upload_path,
            data=file_content,
            content_type="application/octet-stream",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(put_resp.status_code, status.HTTP_200_OK)

        # Verify TrainingOutput created
        output = TrainingOutput.objects.filter(job=self.job, relative_path="artifacts/model/model.pkl").first()
        self.assertIsNotNone(output)
        self.assertEqual(output.kind, "model")
        self.assertEqual(output.size_bytes, len(file_content))

        # 2. GET download
        get_resp = self.client.get(
            upload_path,
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)
        content = b"".join(get_resp.streaming_content) if hasattr(get_resp, "streaming_content") else get_resp.content
        self.assertEqual(content, file_content)

    def test_mlflow_artifact_proxy_list_and_rest_list(self):
        # Upload two files under model/
        base_url = (
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/users/{self.user.tenant_id}/models/"
            f"{self.project.public_id}/training/jobs/{self.job.public_id}/mlflow/artifacts/model"
        )
        self.client.put(
            f"{base_url}/MLmodel",
            data=b"flavors: python_function",
            content_type="text/plain",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.client.put(
            f"{base_url}/weights.bin",
            data=b"\x00\x01\x02\x03",
            content_type="application/octet-stream",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        # 1. Standard MLflow client list (GET /mlflow-artifacts/artifacts?path=...)
        list_url = (
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts?path=users/{self.user.tenant_id}/models/"
            f"{self.project.public_id}/training/jobs/{self.job.public_id}/mlflow/artifacts/model"
        )
        resp = self.client.get(list_url, HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        files = {f["path"]: f for f in resp.data["files"]}
        self.assertIn("MLmodel", files)
        self.assertIn("weights.bin", files)
        self.assertFalse(files["MLmodel"]["is_dir"])

        # 2. REST store list (GET /api/2.0/mlflow/artifacts/list?run_id=...&path=model)
        rest_url = f"/api/2.0/mlflow/artifacts/list?run_id={self.job.public_id}&path=model"
        rest_resp = self.client.get(rest_url, HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(rest_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(rest_resp.data["root_uri"].startswith("mlflow-artifacts:/"))
        rest_files = {f["path"]: f for f in rest_resp.data["files"]}
        self.assertIn("MLmodel", rest_files)
        self.assertIn("weights.bin", rest_files)

    def test_mlflow_artifact_proxy_delete(self):
        file_path = (
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/users/{self.user.tenant_id}/models/"
            f"{self.project.public_id}/training/jobs/{self.job.public_id}/mlflow/artifacts/temp_file.txt"
        )
        self.client.put(
            file_path,
            data=b"to be deleted",
            content_type="text/plain",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertTrue(TrainingOutput.objects.filter(job=self.job, relative_path="artifacts/temp_file.txt").exists())

        del_resp = self.client.delete(file_path, HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(del_resp.status_code, status.HTTP_200_OK)
        self.assertFalse(TrainingOutput.objects.filter(job=self.job, relative_path="artifacts/temp_file.txt").exists())

    def test_mlflow_artifact_proxy_cross_tenant_forbidden(self):
        User = get_user_model()
        attacker = User.objects.create_user("attacker@example.com", "password123", tenant_id="tenant-attacker")
        attacker_proj = ModelProject.objects.create(owner=attacker, name="attacker-proj")
        attacker_job = TrainingJob.objects.create(project=attacker_proj, name="attacker-job", status="running")
        attacker_token = issue_capability(attacker_job, "tracking")

        target_url = (
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/users/{self.user.tenant_id}/models/"
            f"{self.project.public_id}/training/jobs/{self.job.public_id}/mlflow/artifacts/secret.txt"
        )

        # Attacker tries to upload to victim's path
        put_resp = self.client.put(
            target_url,
            data=b"malicious payload",
            content_type="text/plain",
            HTTP_AUTHORIZATION=f"Bearer {attacker_token}",
        )
        self.assertEqual(put_resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(put_resp.data["error_code"], "PERMISSION_DENIED")

    def test_mlflow_multipart_upload_fallback_501(self):
        mpu_url = (
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/mpu/create/users/{self.user.tenant_id}/models/"
            f"{self.project.public_id}/training/jobs/{self.job.public_id}/mlflow/artifacts/model/weights.bin"
        )
        resp = self.client.post(
            mpu_url,
            data={"path": "model/weights.bin", "num_parts": 5},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(resp.status_code, status.HTTP_501_NOT_IMPLEMENTED)
        self.assertEqual(resp.data["error_code"], "NOT_IMPLEMENTED")
        self.assertIn("Multipart upload is not supported for the current artifact repository", resp.data["message"])

    def test_mlflow_root_artifact_proxy_url(self):
        root_url = (
            f"/api/2.0/mlflow-artifacts/artifacts/users/{self.user.tenant_id}/models/"
            f"{self.project.public_id}/training/jobs/{self.job.public_id}/mlflow/artifacts/root_test.json"
        )
        put_resp = self.client.put(
            root_url,
            data=b'{"version": 1}',
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(put_resp.status_code, status.HTTP_200_OK)

        get_resp = self.client.get(root_url, HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)
        content = b"".join(get_resp.streaming_content) if hasattr(get_resp, "streaming_content") else get_resp.content
        self.assertEqual(content, b'{"version": 1}')

    def test_mlflow_runs_update_does_not_prematurely_complete_job(self):
        """
        Verify that ending/updating an MLflow run via runs/update does NOT
        prematurely mark TrainingJob.status as 'completed'. The TrainingJob
        lifecycle must be managed strictly by callbacks/observers.
        """
        self.assertEqual(self.job.status, "running")

        resp = self.client.post(
            "/api/2.0/mlflow/runs/update",
            data={
                "run_id": str(self.job.public_id),
                "status": "FINISHED",
                "end_time": 1700000000000,
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["run_info"]["status"], "FINISHED")

        # Crucial check: TrainingJob.status must STILL be 'running'
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "running")
        self.assertIsNone(self.job.completed_at)
        self.assertEqual(self.job.tracking.get("mlflow_status"), "FINISHED")
        self.assertEqual(self.job.tracking.get("end_time"), 1700000000000)

        # But runs/get reports FINISHED to MLflow client
        get_resp = self.client.get(
            f"/api/2.0/mlflow/runs/get?run_id={self.job.public_id}",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(get_resp.data["run"]["info"]["status"], "FINISHED")
        self.assertEqual(get_resp.data["run"]["info"]["end_time"], 1700000000000)

    def test_capability_token_cannot_access_other_job_same_tenant(self):
        """
        Verify that a capability token issued for Job A CANNOT access, mutate, or log
        metrics/params/tags/artifacts for Job B, even though both jobs belong to the same tenant.
        """
        job_b = TrainingJob.objects.create(
            project=self.project,
            name="job-b-same-tenant",
            model_flavor="sklearn",
            status="running",
        )

        headers = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

        # 1. Log metric on Job B
        resp = self.client.post(
            "/api/2.0/mlflow/runs/log-metric",
            data={"run_id": str(job_b.public_id), "key": "val_loss", "value": 0.25},
            format="json",
            **headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["error_code"], "PERMISSION_DENIED")
        self.assertIn("Capability token is only authorized for its assigned job", resp.data["message"])

        # 2. Log param on Job B
        resp = self.client.post(
            "/api/2.0/mlflow/runs/log-parameter",
            data={"run_id": str(job_b.public_id), "key": "lr", "value": "0.01"},
            format="json",
            **headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["error_code"], "PERMISSION_DENIED")

        # 3. Set tag on Job B
        resp = self.client.post(
            "/api/2.0/mlflow/runs/set-tag",
            data={"run_id": str(job_b.public_id), "key": "tag_name", "value": "tag_val"},
            format="json",
            **headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["error_code"], "PERMISSION_DENIED")

        # 4. Update status on Job B
        resp = self.client.post(
            "/api/2.0/mlflow/runs/update",
            data={"run_id": str(job_b.public_id), "status": "KILLED"},
            format="json",
            **headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["error_code"], "PERMISSION_DENIED")

        # 5. Get run Job B
        resp = self.client.get(
            f"/api/2.0/mlflow/runs/get?run_id={job_b.public_id}",
            **headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["error_code"], "PERMISSION_DENIED")

        # 6. List artifacts on Job B
        resp = self.client.get(
            f"/api/2.0/mlflow/artifacts/list?run_id={job_b.public_id}",
            **headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["error_code"], "PERMISSION_DENIED")

        # 7. Upload artifact to Job B proxy path
        resp = self.client.put(
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/users/{self.user.tenant_id}/models/{self.project.public_id}/training/jobs/{job_b.public_id}/mlflow/artifacts/malicious.txt",
            data=b"malicious content",
            content_type="text/plain",
            **headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["error_code"], "PERMISSION_DENIED")

    def test_api_key_allowed_projects_enforcement(self):
        """
        Verify that a UserAPIKey scoped with allowed_projects is strictly restricted
        to those projects, and rejected (403 PERMISSION_DENIED) when trying to access or create
        runs/experiments/artifacts outside its allowed projects.
        """
        project2 = ModelProject.objects.create(
            owner=self.user,
            name="project-two-private",
        )
        job_in_project2 = TrainingJob.objects.create(
            project=project2,
            name="job-in-project2",
            model_flavor="sklearn",
            status="running",
        )

        raw_key, prefix, key_hash = UserAPIKey.issue()
        api_key = UserAPIKey.objects.create(
            user=self.user,
            name="scoped-api-key",
            key_prefix=prefix,
            key_hash=key_hash,
        )
        # Authorize key ONLY for self.project
        api_key.allowed_projects.set([self.project])

        headers = {"HTTP_AUTHORIZATION": f"Bearer {raw_key}"}

        # --- Allowed operations on self.project / self.job ---
        resp = self.client.get(
            f"/api/2.0/mlflow/runs/get?run_id={self.job.public_id}",
            **headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.post(
            "/api/2.0/mlflow/runs/log-metric",
            data={"run_id": str(self.job.public_id), "key": "accuracy", "value": 0.98},
            format="json",
            **headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # --- Forbidden operations on project2 / job_in_project2 ---
        # 1. Get run in project2
        resp = self.client.get(
            f"/api/2.0/mlflow/runs/get?run_id={job_in_project2.public_id}",
            **headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["error_code"], "PERMISSION_DENIED")

        # 2. Log metric to job in project2
        resp = self.client.post(
            "/api/2.0/mlflow/runs/log-metric",
            data={"run_id": str(job_in_project2.public_id), "key": "loss", "value": 0.1},
            format="json",
            **headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["error_code"], "PERMISSION_DENIED")

        # 3. Create run under project2
        resp = self.client.post(
            "/api/2.0/mlflow/runs/create",
            data={"experiment_id": str(project2.public_id), "run_name": "forbidden-run"},
            format="json",
            **headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["error_code"], "PERMISSION_DENIED")

        # 4. Get experiment for project2
        resp = self.client.get(
            f"/api/2.0/mlflow/experiments/get?experiment_id={project2.public_id}",
            **headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["error_code"], "PERMISSION_DENIED")

        # 5. Get experiment by name for project2
        resp = self.client.get(
            f"/api/2.0/mlflow/experiments/get-by-name?experiment_name={project2.name}",
            **headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["error_code"], "PERMISSION_DENIED")

        # 6. Restricted key cannot create brand new experiments
        resp = self.client.post(
            "/api/2.0/mlflow/experiments/create",
            data={"name": "brand-new-exp"},
            format="json",
            **headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["error_code"], "PERMISSION_DENIED")

        # 7. Upload artifact to job in project2
        resp = self.client.put(
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/users/{self.user.tenant_id}/models/{project2.public_id}/training/jobs/{job_in_project2.public_id}/mlflow/artifacts/model.bin",
            data=b"model binary",
            content_type="application/octet-stream",
            **headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["error_code"], "PERMISSION_DENIED")

    def test_mlflow_artifact_proxy_streaming_download(self):
        """
        Verify that downloading an artifact via proxy uses StreamingHttpResponse
        and streams the content properly without buffering the entire file into RAM.
        """
        upload_url = (
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/users/{self.user.tenant_id}/"
            f"models/{self.project.public_id}/training/jobs/{self.job.public_id}/mlflow/artifacts/test_stream.bin"
        )
        test_content = b"streaming-payload-" * 1000  # ~18 KB test payload

        put_resp = self.client.put(
            upload_url,
            data=test_content,
            content_type="application/octet-stream",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(put_resp.status_code, status.HTTP_200_OK)

        get_resp = self.client.get(upload_url, HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(getattr(get_resp, "streaming", False))
        content = b"".join(get_resp.streaming_content) if hasattr(get_resp, "streaming_content") else get_resp.content
        self.assertEqual(content, test_content)

    def test_mlflow_artifact_proxy_presigned_download(self):
        """
        Verify that adding ?presigned=true generates a direct presigned download URL.
        """
        upload_url = (
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/users/{self.user.tenant_id}/"
            f"models/{self.project.public_id}/training/jobs/{self.job.public_id}/mlflow/artifacts/test_presigned.bin"
        )
        self.client.put(
            upload_url,
            data=b"presigned-target-data",
            content_type="application/octet-stream",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        presigned_req_url = f"{upload_url}?presigned=true"
        get_resp = self.client.get(presigned_req_url, HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)
        self.assertIn("download_url", get_resp.data)
        self.assertTrue(get_resp.data["download_url"].startswith("https://"))

    def test_mlflow_artifact_proxy_download_size_limit_exceeded(self):
        """
        Verify that when an artifact exceeds the download size limit, the endpoint
        returns a clear 413 MAX_SIZE_EXCEEDED error instead of masking it as a 404.
        """
        upload_url = (
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/users/{self.user.tenant_id}/"
            f"models/{self.project.public_id}/training/jobs/{self.job.public_id}/mlflow/artifacts/large_model.bin"
        )
        # Upload a 200-byte artifact
        self.client.put(
            upload_url,
            data=b"x" * 200,
            content_type="application/octet-stream",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        # Set max download limit to 100 bytes (lower than 200 bytes)
        with self.settings(MLFLOW_MAX_ARTIFACT_DOWNLOAD_SIZE_BYTES=100):
            get_resp = self.client.get(upload_url, HTTP_AUTHORIZATION=f"Bearer {self.token}")
            self.assertEqual(get_resp.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
            self.assertEqual(get_resp.data["error_code"], "MAX_SIZE_EXCEEDED")
            self.assertIn("exceeds maximum allowed limit", get_resp.data["message"])

    def test_mlflow_artifact_proxy_upload_size_limit_exceeded(self):
        """
        Verify that when an uploaded artifact exceeds the upload size limit, the endpoint
        rejects it with a clear 413 MAX_SIZE_EXCEEDED error.
        """
        upload_url = (
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/users/{self.user.tenant_id}/"
            f"models/{self.project.public_id}/training/jobs/{self.job.public_id}/mlflow/artifacts/huge_model.bin"
        )
        # Set max upload limit to 100 bytes
        with self.settings(MLFLOW_MAX_ARTIFACT_UPLOAD_SIZE_BYTES=100):
            put_resp = self.client.put(
                upload_url,
                data=b"y" * 200,
                content_type="application/octet-stream",
                HTTP_AUTHORIZATION=f"Bearer {self.token}",
            )
            self.assertEqual(put_resp.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
            self.assertEqual(put_resp.data["error_code"], "MAX_SIZE_EXCEEDED")
            self.assertIn("exceeds maximum allowed limit", put_resp.data["message"])

    def test_tracking_capability_revoked_on_mark_finished_and_mutations_blocked(self):
        """
        Verify that marking a job finished (terminal state) revokes its tracking capabilities,
        and requests using that token are rejected with 401 UNAUTHENTICATED.
        """
        self.assertTrue(TrainingJobCapability.objects.filter(job=self.job, purpose="tracking").exists())

        self.job.mark_finished("completed")
        self.job.save(update_fields=["status", "completed_at", "runtime_seconds", "updated_at"])

        # Tracking capability must be deleted from the database
        self.assertFalse(TrainingJobCapability.objects.filter(job=self.job, purpose="tracking").exists())

        # Any subsequent tracking request using the revoked token must fail with 401
        resp = self.client.post(
            "/api/2.0/mlflow/runs/log-metric",
            data={"run_id": str(self.job.public_id), "key": "val_loss", "value": 0.42},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(resp.data["error_code"], "UNAUTHENTICATED")

    def test_terminal_job_mutation_blocked_with_invalid_state(self):
        """
        Verify that even if an authenticated API key is used, mutation endpoints
        (metrics, params, tags, status updates, upload URLs, artifact PUT, artifact DELETE)
        reject mutations on terminal jobs (completed, failed, cancelled) with 400 INVALID_STATE.
        """
        raw_key, prefix, key_hash = UserAPIKey.issue()
        UserAPIKey.objects.create(
            user=self.user,
            name="scientist-key",
            key_prefix=prefix,
            key_hash=key_hash,
        )
        api_headers = {"HTTP_AUTHORIZATION": f"Bearer {raw_key}"}

        # Mark job completed
        self.job.mark_finished("completed")
        self.job.save(update_fields=["status", "completed_at", "runtime_seconds", "updated_at"])

        run_id = str(self.job.public_id)

        # 1. log-metric
        resp = self.client.post(
            "/api/2.0/mlflow/runs/log-metric",
            data={"run_id": run_id, "key": "acc", "value": 0.99},
            format="json",
            **api_headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["error_code"], "INVALID_STATE")

        # 2. log-batch
        resp = self.client.post(
            "/api/2.0/mlflow/runs/log-batch",
            data={"run_id": run_id, "metrics": [{"key": "acc", "value": 0.99}]},
            format="json",
            **api_headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["error_code"], "INVALID_STATE")

        # 3. log-parameter
        resp = self.client.post(
            "/api/2.0/mlflow/runs/log-parameter",
            data={"run_id": run_id, "key": "lr", "value": "0.01"},
            format="json",
            **api_headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["error_code"], "INVALID_STATE")

        # 4. set-tag
        resp = self.client.post(
            "/api/2.0/mlflow/runs/set-tag",
            data={"run_id": run_id, "key": "env", "value": "prod"},
            format="json",
            **api_headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["error_code"], "INVALID_STATE")

        # 5. runs/update
        resp = self.client.post(
            "/api/2.0/mlflow/runs/update",
            data={"run_id": run_id, "status": "FAILED"},
            format="json",
            **api_headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["error_code"], "INVALID_STATE")

        # 6. artifacts/upload-url
        resp = self.client.post(
            "/api/2.0/mlflow/artifacts/upload-url",
            data={"run_id": run_id, "path": "model.pkl"},
            format="json",
            **api_headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["error_code"], "INVALID_STATE")

        # 7. Artifact proxy PUT
        artifact_path = (
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/users/{self.user.tenant_id}/"
            f"models/{self.project.public_id}/training/jobs/{self.job.public_id}/mlflow/artifacts/model.pkl"
        )
        resp = self.client.put(
            artifact_path,
            data=b"model-data",
            content_type="application/octet-stream",
            **api_headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["error_code"], "INVALID_STATE")

        # 8. Artifact proxy DELETE
        resp = self.client.delete(
            artifact_path,
            **api_headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["error_code"], "INVALID_STATE")

    def test_completed_job_reads_remain_accessible(self):
        """
        Verify that read operations (runs/get, metrics history, artifacts/list, artifact download)
        remain fully functional for completed jobs.
        """
        raw_key, prefix, key_hash = UserAPIKey.issue()
        UserAPIKey.objects.create(
            user=self.user,
            name="read-key",
            key_prefix=prefix,
            key_hash=key_hash,
        )
        api_headers = {"HTTP_AUTHORIZATION": f"Bearer {raw_key}"}

        # First, upload an artifact while running
        artifact_url = (
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/users/{self.user.tenant_id}/"
            f"models/{self.project.public_id}/training/jobs/{self.job.public_id}/mlflow/artifacts/result.txt"
        )
        self.client.put(
            artifact_url,
            data=b"successful training output",
            content_type="text/plain",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        # Log a metric while running
        TrainingJobMetric.objects.create(job=self.job, name="final_loss", value=0.15, step=10)

        # Mark job completed
        self.job.mark_finished("completed")
        self.job.save(update_fields=["status", "completed_at", "runtime_seconds", "updated_at"])

        run_id = str(self.job.public_id)

        # 1. runs/get
        resp = self.client.get(f"/api/2.0/mlflow/runs/get?run_id={run_id}", **api_headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["run"]["info"]["run_id"], run_id)

        # 2. metrics/get-history
        resp = self.client.get(f"/api/2.0/mlflow/metrics/get-history?run_id={run_id}&metric_key=final_loss", **api_headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["metrics"]), 1)
        self.assertEqual(resp.data["metrics"][0]["value"], 0.15)

        # 3. artifacts/list
        resp = self.client.get(f"/api/2.0/mlflow/artifacts/list?run_id={run_id}", **api_headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(any(f["path"] == "result.txt" for f in resp.data["files"]))

        # 4. Artifact proxy GET (download)
        resp = self.client.get(artifact_url, **api_headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        content = b"".join(resp.streaming_content) if resp.streaming else resp.content
        self.assertEqual(content, b"successful training output")

    def test_job_cancellation_and_deletion_revokes_tracking_and_blocks_mutation(self):
        """
        Verify that cancel_job and request_job_deletion revoke tracking capability
        and block any subsequent mutations.
        """
        self.assertTrue(TrainingJobCapability.objects.filter(job=self.job, purpose="tracking").exists())

        cancel_job(self.job)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "cancelling")
        self.assertFalse(TrainingJobCapability.objects.filter(job=self.job, purpose="tracking").exists())

        raw_key, prefix, key_hash = UserAPIKey.issue()
        UserAPIKey.objects.create(
            user=self.user,
            name="cancel-test-key",
            key_prefix=prefix,
            key_hash=key_hash,
        )
        api_headers = {"HTTP_AUTHORIZATION": f"Bearer {raw_key}"}

        # Mutations on cancelling job must be blocked
        resp = self.client.post(
            "/api/2.0/mlflow/runs/log-metric",
            data={"run_id": str(self.job.public_id), "key": "loss", "value": 0.5},
            format="json",
            **api_headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["error_code"], "INVALID_STATE")

    def test_capability_token_auto_revocation_on_auth_for_terminal_job(self):
        """
        Verify that if a capability token exists in DB for a job that later transitioned
        to a terminal state (or deletion), authenticate_mlflow_request cleans up the token
        and returns 401 UNAUTHENTICATED.
        """
        # Re-issue a token directly
        token = issue_capability(self.job, "tracking")
        self.job.status = "failed"
        self.job.save(update_fields=["status"])

        resp = self.client.get(
            f"/api/2.0/mlflow/runs/get?run_id={self.job.public_id}",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(resp.data["error_code"], "UNAUTHENTICATED")

        # The capability must be automatically revoked/deleted from DB
        self.assertFalse(TrainingJobCapability.objects.filter(job=self.job, purpose="tracking").exists())

    def test_experiment_level_artifact_listing(self):
        """
        Verify that querying the artifact proxy at the experiment-level URI
        returns a directory listing of all jobs (runs) under that experiment.
        """
        job_2 = TrainingJob.objects.create(
            project=self.project,
            name="job-run-2",
            model_flavor="sklearn",
            status="running",
        )

        exp_artifact_path = (
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/users/{self.user.tenant_id}/"
            f"models/{self.project.public_id}/training/jobs"
        )
        resp = self.client.get(exp_artifact_path, HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        paths = [f["path"] for f in resp.data["files"]]
        self.assertIn(str(self.job.public_id), paths)
        self.assertIn(str(job_2.public_id), paths)
        for f in resp.data["files"]:
            self.assertTrue(f["is_dir"])

    def test_experiment_derived_run_artifact_upload_and_download(self):
        """
        Verify that client paths derived from the experiment-level URI
        (e.g., .../training/jobs/<job_id>/artifacts/<path>, without '/mlflow/')
        can be uploaded, downloaded, and listed via the proxy.
        """
        file_data = b"model-weights-derived-from-experiment"
        upload_path = (
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/users/{self.user.tenant_id}/models/"
            f"{self.project.public_id}/training/jobs/{self.job.public_id}/artifacts/weights.bin"
        )

        # 1. Upload via experiment-derived path
        put_resp = self.client.put(
            upload_path,
            data=file_data,
            content_type="application/octet-stream",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(put_resp.status_code, status.HTTP_200_OK)

        # 2. Download via experiment-derived path
        get_resp = self.client.get(upload_path, HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)
        content = b"".join(get_resp.streaming_content) if get_resp.streaming else get_resp.content
        self.assertEqual(content, file_data)

        # 3. Directory listing of job artifacts via experiment-derived path
        dir_path = (
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/users/{self.user.tenant_id}/models/"
            f"{self.project.public_id}/training/jobs/{self.job.public_id}/artifacts"
        )
        list_resp = self.client.get(dir_path, HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(any(f["path"] == "weights.bin" for f in list_resp.data["files"]))

    def test_experiment_level_upload_and_delete_rejected(self):
        """
        Verify that attempting to upload or delete artifacts directly at the
        experiment-level path (without a job ID) returns 400 with a clear error message.
        """
        exp_artifact_path = (
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/users/{self.user.tenant_id}/"
            f"models/{self.project.public_id}/training/jobs"
        )

        put_resp = self.client.put(
            exp_artifact_path,
            data=b"direct experiment upload",
            content_type="application/octet-stream",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(put_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(put_resp.data["error_code"], "INVALID_PARAMETER_VALUE")
        self.assertIn("job ID", put_resp.data["message"])

        del_resp = self.client.delete(exp_artifact_path, HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(del_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(del_resp.data["error_code"], "INVALID_PARAMETER_VALUE")
        self.assertIn("job ID", del_resp.data["message"])



