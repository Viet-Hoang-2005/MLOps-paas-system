"""Tenant-scoped, ephemeral resource snapshots for training runtimes."""

import json
import math
import time
import uuid
from datetime import datetime, timezone

import docker
from django.core.cache import cache

from apps.training.services import local_gpu
from infrastructure.docker_metrics import parse_stats
from infrastructure.execution.job_containers import labels_for
from infrastructure.http import HttpClient
from infrastructure.prometheus import PrometheusClient

INTERVALS = {"docker": 15, "argo": 30}
MAX_AGE = 90


def _finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (TypeError, ValueError):
        return None


def _percent(used, limit):
    if used is None or not limit or used < 0:
        return None
    return round(used / limit * 100, 2)


def _empty(job):
    return {
        "job_id": str(job.public_id),
        "status": "waiting",
        "backend": job.backend,
        "poll_interval_seconds": INTERVALS.get(job.backend, 30),
        "latest": None,
    }


def _point(job):
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cpu_percent": None,
        "cpu_limit_cores": job.vcpu,
        "memory_used_mb": None,
        "memory_limit_mb": job.memory_mb,
        "memory_percent": None,
        "gpu_percent": None,
        "gpu_memory_used_mb": None,
        "gpu_memory_total_mb": None,
        "gpu_memory_percent": None,
    }


def _fill_gpu(point, utilization, used, total):
    utilization, used, total = _finite(utilization), _finite(used), _finite(total)
    point["gpu_percent"] = utilization if utilization is not None and utilization <= 100 else None
    used = used if used is not None and used <= 1_048_576 else None
    total = total if total is not None and total <= 1_048_576 else None
    point["gpu_memory_used_mb"] = used
    point["gpu_memory_total_mb"] = total if total and (used is None or used <= total) else None
    point["gpu_memory_percent"] = _percent(used, point["gpu_memory_total_mb"])


def _docker_snapshot(job):
    client = docker.from_env(timeout=3)
    try:
        container = client.containers.get(f"training-{job.public_id}")
        container.reload()
        labels = container.attrs.get("Config", {}).get("Labels") or {}
        if (
            container.attrs.get("State", {}).get("Status") != "running"
            or not job.external_job_id
            or container.id != job.external_job_id
            or any(labels.get(k) != v for k, v in labels_for(job, "training").items())
        ):
            return None
        stats = parse_stats(container.stats(stream=False))
    finally:
        client.close()
    point = _point(job)
    point["cpu_percent"] = _percent(stats["cpu"], job.vcpu)
    point["memory_used_mb"] = stats["memory"]
    point["memory_percent"] = _percent(stats["memory"], job.memory_mb)
    if job.accelerator_type == "gpu" and job.local_gpu_id:
        gpu = local_gpu.device_metrics(job.local_gpu_id)
        if gpu:
            _fill_gpu(point, gpu["gpu_percent"], gpu["gpu_memory_used_mb"], gpu["gpu_memory_total_mb"])
    return point


def _vector(client, expression, *, pod=None, gpu=False):
    rows = client.query(expression)
    # Refuse ambiguity and never infer a GPU from a node alone.
    if len(rows) != 1:
        if gpu and len(rows) > 1:
            raise ValueError("Ambiguous GPU mapping")
        return None
    row = rows[0]
    labels = row.get("metric", {})
    value = row.get("value", [])
    if len(value) != 2 or _finite(value[0]) is None or not -5 <= time.time() - float(value[0]) <= MAX_AGE:
        return None
    if pod and (labels.get("namespace") != "mlops-paas-training" or labels.get("pod") != pod):
        return None
    if gpu and (labels.get("container") != "node" or not labels.get("UUID")):
        return None
    number = _finite(value[1])
    return (number, labels) if number is not None else None


def _prometheus_snapshot(job, client=None):
    client = client or PrometheusClient(http=HttpClient(timeout=(1, 2)))
    if not client.enabled:
        return None
    ns = "mlops-paas-training"
    scope = {
        "namespace": ns,
        "label_mlops_paas_io_training_job_id": str(job.public_id),
        "label_mlops_paas_io_tenant_id": str(job.owner.tenant_id),
    }
    if job.runtime_project_id:
        scope["label_mlops_paas_io_project_id"] = job.runtime_project_id
    selector = ",".join(f"{k}={json.dumps(v)}" for k, v in scope.items())
    pods = client.query(f"max by (namespace,pod) (kube_pod_labels{{{selector}}})")
    if len(pods) != 1:
        return None
    pod = pods[0].get("metric", {}).get("pod")
    if not pod or pods[0].get("metric", {}).get("namespace") != ns:
        return None
    labels = f'namespace={json.dumps(ns)},pod={json.dumps(pod)},container="node"'
    cgroup = f'{labels},job="kubelet",metrics_path="/metrics/cadvisor"'
    # Rate requires two scrapes; the freshness guard rejects stale cAdvisor/DCGM samples.
    cpu_base = f"container_cpu_usage_seconds_total{{{cgroup}}}"
    memory_base = f"container_memory_working_set_bytes{{{cgroup}}}"
    cpu = _vector(
        client,
        f"max by (namespace,pod,container) (rate({cpu_base}[2m]) and (time() - timestamp({cpu_base}) < {MAX_AGE}))",
        pod=pod,
    )
    memory = _vector(
        client,
        f"max by (namespace,pod,container) ({memory_base} and (time() - timestamp({memory_base}) < {MAX_AGE}))",
        pod=pod,
    )
    point = _point(job)
    point["cpu_percent"] = _percent(cpu[0], job.vcpu) if cpu else None
    point["memory_used_mb"] = memory[0] / 1048576 if memory else None
    point["memory_percent"] = _percent(point["memory_used_mb"], job.memory_mb)
    if job.accelerator_type == "gpu":
        try:
            values = []
            for metric in (
                "DCGM_FI_DEV_GPU_UTIL",
                "DCGM_FI_DEV_FB_USED",
                "DCGM_FI_DEV_FB_FREE",
                "DCGM_FI_DEV_FB_RESERVED",
            ):
                base = f"{metric}{{{labels}}}"
                expression = (
                    f"max by (namespace,pod,container,UUID) ({base} and (time() - timestamp({base}) < {MAX_AGE}))"
                )
                values.append(_vector(client, expression, pod=pod, gpu=True))
            present = [value for value in values if value]
            if present and len({value[1]["UUID"] for value in present}) == 1:
                util = values[0][0] if values[0] else None
                used = values[1][0] if values[1] else None
                free = values[2][0] if values[2] else None
                reserved = values[3][0] if values[3] else None
                total = used + free + reserved if all(v is not None for v in (used, free, reserved)) else None
                _fill_gpu(point, util, used, total)
        except Exception:
            pass  # A broken GPU exporter must not hide CPU and RAM.
    return point


def runtime_metrics(job):
    result = _empty(job)
    if job.status != "running":
        return result
    if job.backend not in INTERVALS:
        return {**result, "status": "unavailable"}
    key = f"training:runtime-metrics:v1:{job.public_id}"
    lock_key = f"{key}:lock"
    token = uuid.uuid4().hex
    try:
        cached = cache.get(key)
        if cached is not None:
            return cached
        if not cache.add(lock_key, token, timeout=90):
            return result
        try:
            cached = cache.get(key)
            if cached is not None:
                return cached
            point = _docker_snapshot(job) if job.backend == "docker" else _prometheus_snapshot(job)
            has_data = point and any(
                point[k] is not None for k in ("cpu_percent", "memory_used_mb", "gpu_percent", "gpu_memory_used_mb")
            )
            result = {**result, "status": "available" if has_data else "waiting", "latest": point if has_data else None}
            cache.set(key, result, timeout=INTERVALS[job.backend])
            return result
        finally:
            if cache.get(lock_key) == token:
                cache.delete(lock_key)
    except Exception:
        # Never expose Docker/Prometheus errors containing infrastructure details.
        return {**result, "status": "unavailable"}
