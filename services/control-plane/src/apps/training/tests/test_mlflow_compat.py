import hashlib
from unittest.mock import patch
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.access.models import UserAPIKey
from apps.catalog.models import ModelProject
from apps.training.models import (
    TrainingJob,
    TrainingJobMetric,
    TrainingJobParam,
    TrainingJobTag,
    TrainingOutput,
)
from apps.training.services.capabilities import issue_capability
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

    def presigned_put(self, uri, expires_in=900):
        return f"https://s3.mock.upload/{uri}"


class MLflowCompatibilityTests(APITestCase):
    def setUp(self):
        self.mock_storage = MockS3Storage()
        self.storage_patcher = patch("apps.training.api.mlflow_compat.S3Storage", lambda: self.mock_storage)
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

    def test_mlflow_runs_create_with_api_key(self):
        raw_key, prefix, key_hash = UserAPIKey.issue()
        UserAPIKey.objects.create(
            user=self.user,
            name="ci-key",
            key_prefix=prefix,
            key_hash=key_hash,
        )

        response = self.client.post(
            "/api/2.0/mlflow/runs/create",
            data={"run_name": "external-run-from-laptop"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        new_job_id = response.data["run"]["info"]["run_id"]
        created_job = TrainingJob.objects.get(public_id=new_job_id)
        self.assertEqual(created_job.project.owner.tenant_id, self.user.tenant_id)
        self.assertEqual(created_job.name, "external-run-from-laptop")

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
        expected_prefix = f"mlflow-artifacts:/tenants/{self.user.tenant_id}/jobs/"
        self.assertTrue(create_resp.data["run"]["info"]["artifact_uri"].startswith(expected_prefix))

        # 2. runs/get
        get_resp = self.client.get(
            f"/api/2.0/mlflow/runs/get?run_id={self.job.public_id}",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)
        expected_uri = f"mlflow-artifacts:/tenants/{self.user.tenant_id}/jobs/{self.job.public_id}/artifacts"
        self.assertEqual(get_resp.data["run"]["info"]["artifact_uri"], expected_uri)

    def test_mlflow_artifact_proxy_upload_and_download(self):
        file_content = b"pickle-serialized-model-bytes-123456789"
        upload_path = (
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/tenants/"
            f"{self.user.tenant_id}/jobs/{self.job.public_id}/artifacts/model/model.pkl"
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
        self.assertEqual(get_resp.content, file_content)

    def test_mlflow_artifact_proxy_list_and_rest_list(self):
        # Upload two files under model/
        base_url = (
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/tenants/"
            f"{self.user.tenant_id}/jobs/{self.job.public_id}/artifacts/model"
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
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts?path=tenants/"
            f"{self.user.tenant_id}/jobs/{self.job.public_id}/artifacts/model"
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
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/tenants/"
            f"{self.user.tenant_id}/jobs/{self.job.public_id}/artifacts/temp_file.txt"
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
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/tenants/"
            f"{self.user.tenant_id}/jobs/{self.job.public_id}/artifacts/secret.txt"
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
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/mpu/create/tenants/"
            f"{self.user.tenant_id}/jobs/{self.job.public_id}/artifacts/model/weights.bin"
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
            f"/api/2.0/mlflow-artifacts/artifacts/tenants/"
            f"{self.user.tenant_id}/jobs/{self.job.public_id}/artifacts/root_test.json"
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
        self.assertEqual(get_resp.content, b'{"version": 1}')

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
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/tenants/{self.user.tenant_id}/jobs/{job_b.public_id}/artifacts/malicious.txt",
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
            f"/api/2.0/mlflow/api/2.0/mlflow-artifacts/artifacts/tenants/{self.user.tenant_id}/jobs/{job_in_project2.public_id}/artifacts/model.bin",
            data=b"model binary",
            content_type="application/octet-stream",
            **headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["error_code"], "PERMISSION_DENIED")



