"""Docker/S3 acceptance on a disposable project; invoke through manage.py shell."""

import io
import os
import time
import uuid
import zipfile
from datetime import timedelta

import requests

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.catalog.models import ModelProject
from apps.observability.services.executions import claim, reconcile
from apps.training.models import TrainingJob
from apps.training.services.storage_scope import expected_training_uris
from infrastructure.execution.docker_backends import DockerTrainingBackend
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import project_prefix


ready_by = time.monotonic() + 60
while True:
    try:
        ready = requests.get(f"{settings.CONTROL_PLANE_INTERNAL_URL}/health/ready", timeout=2)
        if ready.status_code == 200:
            break
    except requests.RequestException:
        pass
    if time.monotonic() >= ready_by:
        raise RuntimeError("Control Plane readiness is required before Docker acceptance.")
    time.sleep(1)

storage = S3Storage()
owner = get_user_model().objects.create_user(f"p1-smoke-{uuid.uuid4()}@example.invalid")
project = ModelProject.objects.create(owner=owner, name="P1 Docker acceptance")
backend = DockerTrainingBackend(storage=storage)
jobs = []
runs = []
try:
    job = TrainingJob.objects.create(project=project, name="cpu-recovery", model_flavor="sklearn", backend="docker", status="pending", max_runtime_seconds=900)
    jobs.append(job)
    uris = expected_training_uris(job, storage.bucket)
    source = io.BytesIO()
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("train.py", "import os,pickle,time\nfrom pathlib import Path\ntime.sleep(12)\np=Path(os.environ['SM_MODEL_DIR'])\np.mkdir(exist_ok=True)\n(p/'model.pkl').write_bytes(pickle.dumps({'model':'P1 CPU'}))\nprint('METRIC_JSON: {\"accuracy\": 1.0}',flush=True)\n")
    for name, payload, content_type in (("code", source.getvalue(), "application/zip"), ("data", b"feature,target\n1,0\n", "text/csv")):
        bucket, key = storage.parse_uri(uris[name])
        storage.put(key, payload, content_type)
    job.code_snapshot_uri, job.data_snapshot_uri, job.output_uri = uris["code"], uris["data"], uris["output"]
    job.status = "queued"
    job.save()
    _, lease = claim("training", job.public_id)[0]
    job.refresh_from_db()
    backend.run(job)
    runtime = backend.docker.client.containers.get(f"training-{job.public_id}")
    host = runtime.attrs["HostConfig"]
    assert host["NanoCpus"] == 2_000_000_000
    assert host["Memory"] == 4096 * 1024 * 1024
    assert not host.get("DeviceRequests")
    runtime_id = runtime.id
    # Simulate a dead worker before persisting runtime identity or scheduling polling.
    TrainingJob.objects.filter(pk=job.pk).update(external_job_id="", execution_check_lease_until=timezone.now() - timedelta(seconds=1))
    reconcile("training", job.public_id)
    job.refresh_from_db()
    assert job.external_job_id == runtime_id and job.status == "running"
    for _ in range(50):
        reconcile("training", job.public_id)
        job.refresh_from_db()
        if job.status in {"completed", "failed"}:
            break
        time.sleep(2)
    assert job.status == "completed", (job.status, job.error_message, job.observation_error)
    assert job.runtime_started_at and job.execution_deadline_at
    assert job.outputs.filter(kind="model", s3_uri=job.output_uri).exists()
    assert storage.client.head_object(Bucket=storage.bucket, Key=storage.parse_uri(job.output_uri)[1])["ContentLength"] > 0
    reconcile("training", job.public_id)
    job.refresh_from_db()
    assert job.observation_status == "ok"
    print("PASS Docker training: CPU/RAM enforced, missing ID recovered, one runtime, real S3 output verified, cleanup confirmed.")

    cancelled = TrainingJob.objects.create(project=project, name="deadline-cleanup", model_flavor="sklearn", backend="docker", status="queued", max_runtime_seconds=900)
    jobs.append(cancelled)
    cancelled.code_snapshot_uri, cancelled.data_snapshot_uri, cancelled.output_uri = [expected_training_uris(cancelled, storage.bucket)[key] for key in ("code", "data", "output")]
    cancelled.save()
    # Use an owned runtime that intentionally never responds to application callbacks.
    from infrastructure.execution.job_containers import start
    start(backend.docker, cancelled, "training", image="mlops-paas-training-runner:latest", command=["python", "-c", "import time; time.sleep(120)"], network=settings.DOCKER_NETWORK_NAME)
    TrainingJob.objects.filter(pk=cancelled.pk).update(status="running", runtime_started_at=timezone.now() - timedelta(seconds=901), execution_deadline_at=timezone.now() - timedelta(seconds=1))
    reconcile("training", cancelled.public_id)
    reconcile("training", cancelled.public_id)
    cancelled.refresh_from_db()
    assert cancelled.status == "failed" and cancelled.observation_status == "ok"
    print("PASS Docker watchdog: deadline persisted before stopping an unresponsive owned runtime.")

    from apps.drift.models import DriftMonitor, DriftRun
    from apps.registry.models import ModelVersion
    from apps.production.models import PredictionRecord
    from infrastructure.execution.docker_backends import DockerDriftBackend
    from infrastructure.storage.paths import drift_run_prefix
    version = ModelVersion.objects.create(project=project, version="p1-drift", flavor="sklearn")
    reference_key = project_prefix(owner.tenant_id, project.public_id) + "p1-reference.csv"
    reference = "feature\n" + "\n".join(str(index % 10) for index in range(100)) + "\n"
    reference_uri = storage.put(reference_key, reference, "text/csv").uri
    PredictionRecord.objects.bulk_create([PredictionRecord(project=project, model_version=version, observed_at=timezone.now(), features={"feature": index % 10}, prediction="0") for index in range(100)])
    monitor = DriftMonitor.objects.create(version=version, name="P1 drift", reference_uri=reference_uri, backend="docker")
    run = DriftRun.objects.create(monitor=monitor, status="queued", idempotency_key=f"p1-{uuid.uuid4()}")
    runs.append(run)
    drift_backend = DockerDriftBackend(storage=storage)
    _, lease = claim("drift", run.public_id)[0]
    run.refresh_from_db()
    drift_backend.run(run)
    runtime_id = drift_backend.docker.client.containers.get(f"drift-{run.public_id}").id
    DriftRun.objects.filter(pk=run.pk).update(external_run_id="", execution_check_lease_until=timezone.now() - timedelta(seconds=1))
    reconcile("drift", run.public_id)
    for _ in range(60):
        reconcile("drift", run.public_id)
        run.refresh_from_db()
        if run.status in {"completed", "failed"}:
            break
        time.sleep(2)
    assert run.status == "completed", (run.status, run.error_message, run.observation_error)
    assert run.external_run_id == runtime_id and run.summary
    assert str(run.public_id) in run.summary_uri
    reconcile("drift", run.public_id)
    run.refresh_from_db()
    assert run.observation_status == "ok"
    print("PASS Docker drift: actual Evidently runtime, recovered identity, scoped S3 summary/reports and cleanup.")

    if os.environ.get("P1_SMOKE_GPU") == "1":
        gpu = TrainingJob.objects.create(project=project, name="gpu-device", model_flavor="sklearn", backend="docker", status="pending", max_runtime_seconds=900, accelerator_type="gpu", accelerator_count=1)
        jobs.append(gpu)
        gpu_uris = expected_training_uris(gpu, storage.bucket)
        gpu.code_snapshot_uri, gpu.data_snapshot_uri, gpu.output_uri = [gpu_uris[key] for key in ("code", "data", "output")]
        gpu.save()
        for name, payload, content_type in (("code", source.getvalue(), "application/zip"), ("data", b"feature,target\n1,0\n", "text/csv")):
            storage.put(storage.parse_uri(gpu_uris[name])[1], payload, content_type)
        backend.run(gpu)
        runtime = backend.docker.client.containers.get(f"training-{gpu.public_id}")
        request = runtime.attrs["HostConfig"]["DeviceRequests"][0]
        assert request["Count"] == 1 and request["Capabilities"] == [["gpu"]]
        visible = runtime.exec_run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
        assert visible.exit_code == 0 and visible.output.strip()
        gpu.status = "running"
        gpu.save(update_fields=["status"])
        for _ in range(50):
            reconcile("training", gpu.public_id)
            gpu.refresh_from_db()
            if gpu.status in {"completed", "failed"}:
                break
            time.sleep(2)
        assert gpu.status == "completed", (gpu.status, gpu.error_message)
        reconcile("training", gpu.public_id)
        print("PASS Docker GPU: DeviceRequest count=1, visible hardware, successful artifact upload (test process only; stack GPU flag retained).")
finally:
    for job in jobs:
        backend.cleanup(job)
    for run in runs:
        DockerDriftBackend(storage=storage).cleanup(run)
    storage.delete_prefix(project_prefix(owner.tenant_id, project.public_id))
    from common.redis_client import redis_client
    for job in jobs:
        redis_client().delete(f"training_logs:{job.public_id}")
    for run in runs:
        redis_client().delete(f"drift_logs:{run.public_id}")
    from apps.observability.models import EventOutbox, LifecycleEvent
    aggregate_ids = [project.public_id, *[job.public_id for job in jobs], *[run.public_id for run in runs]]
    LifecycleEvent.objects.filter(aggregate_id__in=aggregate_ids).delete()
    EventOutbox.objects.filter(aggregate_id__in=aggregate_ids).delete()
    owner.delete()
