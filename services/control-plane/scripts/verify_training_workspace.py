"""Local-only end-to-end smoke test. Run with manage.py shell redirected from this file.

Creates a unique disposable tenant and removes only that tenant's resources.
Never prints credentials, capabilities or signed URLs.
"""
import io
import json
import os
import time
import uuid
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from apps.catalog.models import ModelProject
from apps.training.models import TrainingJob, TrainingOutput, LocalTrainingReservation
from apps.training.services.storage_scope import expected_training_uris
from apps.training.services.logs import delete_training_logs
from infrastructure.execution import training_backend
from infrastructure.storage import S3Storage


def wait_for(check, description, seconds=180):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(2)
    raise RuntimeError("Timed out: " + description)


def verify():
    import requests
    def ready():
        try:
            return requests.get("http://127.0.0.1:8000/health/ready", timeout=3).status_code == 200
        except requests.RequestException:
            return False
    wait_for(ready, "Control Plane readiness")
    owner = get_user_model().objects.create_user(f"workspace-smoke-{uuid.uuid4().hex}@example.test")
    client = APIClient(HTTP_HOST="localhost")
    client.force_authenticate(owner)
    storage = S3Storage()
    jobs = []

    def call(method, path, data=None, expected=200):
        response = getattr(client, method)(path, data, format="multipart" if any(hasattr(value, "read") for value in (data or {}).values()) else "json")
        if response.status_code != expected:
            raise RuntimeError(f"Unexpected HTTP {response.status_code} on {method} {path.split('?')[0]}")
        return response.data

    try:
        capabilities = call("get", "/api/training-jobs/runtime-capabilities/")
        if not capabilities["enabled"]:
            raise RuntimeError("Local training capacity is unavailable.")
        profile = min(capabilities["cpu_profiles"], key=lambda item: item["memory_mb"])
        gpu = next((item for item in capabilities["accelerators"] if item["type"] == "gpu"), None) if os.environ.get("TRAINING_SMOKE_GPU") == "true" else None
        if os.environ.get("TRAINING_SMOKE_GPU") == "true" and not gpu:
            raise RuntimeError("No verified NVIDIA GPU is available for the requested smoke test.")
        workspace = call("post", "/api/training-jobs/", {}, expected=201)
        root = f"/api/training-jobs/{workspace['id']}/"
        revision = workspace["revision"]
        for path, kind, payload in [
            ("data", "folder", None),
            ("data/train.csv", "data", b"x\n1\n"),
            ("requirements.txt", "requirements", b""),
            ("train.py", "script", b'''import os, errno, json
from pathlib import Path
root = Path(os.environ["SM_CHANNEL_TRAIN"])
assert os.statvfs(root).f_flag & os.ST_RDONLY
assert (root / "data" / "train.csv").read_text() == "x\\n1\\n"
try:
    (root / "blocked.txt").write_text("must not succeed")
except OSError as error:
    assert error.errno in {errno.EROFS, errno.EACCES, errno.EPERM}, error.errno
else:
    raise RuntimeError("Input was writable")
assert os.environ["SMOKE_MARKER"] == "workspace"
if os.environ.get("SMOKE_GPU_UUID"):
    import subprocess
    visible = subprocess.check_output(["nvidia-smi", "--query-gpu=uuid", "--format=csv,noheader"], text=True)
    assert visible.strip().splitlines() == [os.environ["SMOKE_GPU_UUID"]], "Unexpected visible NVIDIA device"
    print("EXACT_GPU_UUID_VERIFIED")
Path(os.environ["MLOPS_WORK_DIR"], "scratch.txt").write_text("work is writable")
Path(os.environ["SM_MODEL_DIR"], "model.json").write_text(json.dumps({"smoke": "verified"}))
Path(os.environ["SM_OUTPUT_DIR"], "metrics.json").write_text(json.dumps({"accuracy": 0.9}))
print("READ_ONLY_VERIFIED")
'''),
        ]:
            data = {"revision": revision, "path": path, "kind": kind}
            if payload is not None:
                data["file"] = SimpleUploadedFile(path.split("/")[-1], payload)
            result = call("post", root + "entries/", data, expected=201)
            revision = result["revision"]
        result = call("patch", root, {"revision": revision, "entry_point": "train.py", "environment": {"SMOKE_MARKER": "workspace", **({"SMOKE_GPU_UUID": gpu["device_id"]} if gpu else {})},
            "model_flavor": "sklearn", "vcpu": profile["vcpu"], "memory_mb": profile["memory_mb"],
            "max_runtime_seconds": capabilities["runtime_options_seconds"][0], "accelerator_type": "gpu" if gpu else "none", "accelerator_count": 1 if gpu else 0,
            "local_gpu_id": gpu["device_id"] if gpu else ""})
        payload = {"revision": result["revision"], "run_key": str(uuid.uuid4())}
        job = call("post", root + "submit/", payload, expected=202)
        jobs.append(job["id"])
        assert job["id"] == workspace["id"] and job["project_id"] is None
        replay = call("post", root + "submit/", payload, expected=202)
        assert replay["id"] == job["id"]
        print("SMOKE: unassigned run created; idempotent replay verified", flush=True)

        def completed():
            state = call("get", f"/api/training-jobs/{job['id']}/")
            if state["status"] in {"failed", "cancelled"}:
                raise RuntimeError("Smoke training failed: " + state.get("error_message", "")[-1500:])
            return state if state["status"] == "completed" and state["output_available"] else None
        job = wait_for(completed, "training completion")
        model = TrainingJob.objects.get(public_id=job["id"])
        wait_for(lambda: not LocalTrainingReservation.objects.filter(job_id=model.public_id, active=True).exists(), "runtime cleanup")
        model_bytes = storage.read(model.output_uri, max_bytes=5 * 1024 * 1024)
        import tarfile
        with tarfile.open(fileobj=io.BytesIO(model_bytes), mode="r:gz") as archive:
            assert json.load(archive.extractfile("model.json")) == {"smoke": "verified"}
        assert "READ_ONLY_VERIFIED" in call("get", f"/api/training-jobs/{job['id']}/logs/")["logs"][-20:].__str__()
        print("SMOKE: Input is kernel read-only; Work, model export, upload and cleanup verified", flush=True)
        if gpu:
            assert "EXACT_GPU_UUID_VERIFIED" in str(call("get", f"/api/training-jobs/{job['id']}/logs/")["logs"])
            print("SMOKE: runner sees exactly the selected NVIDIA GPU UUID", flush=True)
        clone_key = {"creation_key": str(uuid.uuid4())}
        clone = call("post", f"/api/training-jobs/{job['id']}/clone/", clone_key, expected=201)
        assert clone["id"] != job["id"] and clone["status"] == "editing" and clone["submitted_at"] is None
        assert clone["project_id"] is None and clone["outputs"] == []
        replay = call("post", f"/api/training-jobs/{job['id']}/clone/", clone_key, expected=201)
        assert replay["id"] == clone["id"]
        copied = call("get", f"/api/training-jobs/{clone['id']}/")
        assert {entry["path"] for entry in copied["entries"]} == {"train.py", "requirements.txt", "data", "data/train.csv"}
        call("delete", f"/api/training-jobs/{clone['id']}/", expected=202)
        wait_for(lambda: not TrainingJob.objects.filter(public_id=clone["id"]).exists(), "Editing clone cleanup")
        print("SMOKE: clone replay, new Editing UUID, frozen Input copy and draft deletion verified", flush=True)
        project_id = str(uuid.uuid4())
        job = call("post", f"/api/training-jobs/{job['id']}/project/", {"output_revision": job["output_revision"],
            "new_project": {"id": project_id, "name": "Disposable smoke project", "access_mode": "private"}})
        project = ModelProject.objects.get(public_id=project_id)

        # A legacy object exercises copy+checksum+pointer migration on real S3.
        legacy = TrainingJob(project=project, owner=owner, model_flavor="sklearn", status="completed", backend="docker", max_runtime_seconds=900, submitted_at=__import__("django.utils.timezone", fromlist=["now"]).now())
        uris = expected_training_uris(legacy, storage.bucket)
        legacy.code_snapshot_uri, legacy.data_snapshot_uri = uris["code"], uris["data"]
        legacy.output_uri, legacy.mlflow_artifact_uri = uris["output"], uris["mlflow"]
        for key, data in (("code", b"source"), ("data", b"data"), ("output", model_bytes)):
            storage.put(storage.parse_uri(uris[key])[1], data)
        legacy.save()
        jobs.append(str(legacy.public_id))
        TrainingOutput.objects.create(job=legacy, kind="model", relative_path="model.tar.gz", s3_uri=legacy.output_uri)
        call("delete", f"/api/models/{project_id}/", expected=202)
        wait_for(lambda: not ModelProject.objects.filter(public_id=project_id).exists(), "Project cleanup")
        for job_id in jobs:
            retained = call("get", f"/api/training-jobs/{job_id}/")
            assert retained["project_id"] is None and retained["output_available"]
        legacy.refresh_from_db()
        assert legacy.storage_layout == "tenant"
        assert storage.read(legacy.output_uri, max_bytes=5 * 1024 * 1024) == model_bytes
        print("SMOKE: Project assignment, legacy storage migration and retained job artifacts verified", flush=True)
    finally:
        stopped = True
        for job in TrainingJob.objects.filter(owner=owner).select_related("owner", "project"):
            try:
                result = training_backend(job.backend).cleanup(job) if job.submitted_at else {"confirmed": True}
                if not result.get("confirmed"):
                    raise RuntimeError("Runtime cleanup is not confirmed.")
                from apps.training.services.local_resources import release
                release(job)
                delete_training_logs(job.public_id)
            except Exception:
                stopped = False
        if not stopped:
            raise RuntimeError("Smoke runtime cleanup is unconfirmed; test tenant retained for recovery.")
        storage.delete_prefix(f"users/{owner.tenant_id}/")
        owner.delete()


verify()
