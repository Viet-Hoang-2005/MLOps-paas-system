"""Bounded, credential-free NVIDIA discovery through the actual Docker runtime."""

import csv
import io
import re
import time
import uuid
from contextlib import contextmanager, suppress
from datetime import datetime, timezone

import docker
import docker.errors
import requests
from django.core.cache import cache
from rest_framework.exceptions import ValidationError

from common.api.exceptions import ServiceUnavailable
from infrastructure.docker import DockerClient

IMAGE = "mlops-paas-training-runner:latest"
CACHE_KEY = "training:local-gpu:inventory:v1"
LOCK_KEY = "training:local-gpu:probe-lock:v1"
GPU_UUID = re.compile(r"^GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
QUERY = ["--query-gpu=uuid,name,memory.total,memory.free", "--format=csv,noheader,nounits"]
METRICS_QUERY = ["--query-gpu=uuid,utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"]
PROBE_PREFIX = "mlops-local-gpu-probe-"


def _result(status, reason="", devices=None):
    return {
        "status": status,
        "reason": reason,
        "devices": devices or [],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _number(value):
    try:
        result = int(value.strip())
        return result if result >= 0 else None
    except (ValueError, AttributeError):
        return None


def _parse(output):
    devices = []
    for row in csv.reader(io.StringIO(output)):
        if len(row) != 4:
            continue
        identifier, name, total, free = (value.strip() for value in row)
        if not GPU_UUID.fullmatch(identifier) or not name:
            continue
        devices.append(
            {"id": identifier, "name": name[:160], "memory_total_mib": _number(total), "memory_free_mib": _number(free)}
        )
    return devices


def _reap_stale(client):
    """Recover probes left behind when Docker became unreachable during cleanup."""
    for container in client.containers.list(all=True, filters={"label": "mlops_paas.gpu_probe=true"}):
        labels = container.attrs.get("Config", {}).get("Labels") or {}
        expires = labels.get("mlops_paas.gpu_probe_expires", "")
        if (
            re.fullmatch(PROBE_PREFIX + r"[0-9a-f]{32}", container.name or "")
            and str(expires).isdigit()
            and int(expires) < time.time()
        ):
            with suppress(Exception):
                container.remove(force=True)


def _probe(device_id=None, client=None, *, metrics=False):
    """Run the same NVIDIA DeviceRequest path as a training container; never pull images."""
    container = None
    name = f"{PROBE_PREFIX}{uuid.uuid4().hex}"
    try:
        client = client or DockerClient(timeout=3).client
        _reap_stale(client)
        client.images.get(IMAGE)
        request = (
            docker.types.DeviceRequest(device_ids=[device_id], capabilities=[["gpu"]])
            if device_id
            else docker.types.DeviceRequest(count=-1, capabilities=[["gpu"]])
        )
        container = client.containers.create(
            IMAGE,
            name=name,
            entrypoint="nvidia-smi",
            command=METRICS_QUERY if metrics else QUERY,
            device_requests=[request],
            network_disabled=True,
            user="10001:10001",
            mem_limit="256m",
            nano_cpus=250_000_000,
            pids_limit=64,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            labels={"mlops_paas.gpu_probe": "true", "mlops_paas.gpu_probe_expires": str(int(time.time()) + 120)},
            detach=True,
        )
        container.start()
        result = container.wait(timeout=5)
        if result.get("StatusCode") != 0:
            return _result("unavailable", "nvidia_unavailable")
        output = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        if metrics:
            rows = list(csv.reader(io.StringIO(output)))
            devices = []
            if len(rows) == 1 and len(rows[0]) == 4:
                identifier, utilization, used, total = (value.strip() for value in rows[0])
                if GPU_UUID.fullmatch(identifier):
                    devices = [
                        {
                            "id": identifier,
                            "gpu_percent": _number(utilization),
                            "gpu_memory_used_mb": _number(used),
                            "gpu_memory_total_mb": _number(total),
                        }
                    ]
        else:
            devices = _parse(output)
        if not devices:
            return _result("unavailable", "nvidia_unavailable")
        if device_id and (len(devices) != 1 or devices[0]["id"] != device_id):
            return _result("unavailable", "device_selection_unsupported")
        return _result("available", devices=devices)
    except docker.errors.ImageNotFound:
        return _result("unavailable", "image_missing")
    except docker.errors.APIError:
        return _result("unavailable", "nvidia_unavailable")
    except (requests.RequestException, OSError, docker.errors.DockerException):
        return _result("error", "docker_unavailable")
    finally:
        if container is not None:
            with suppress(Exception):
                container.remove(force=True)
        elif client is not None:
            # A create request can time out after Docker has created the container.
            with suppress(Exception):
                client.containers.get(name).remove(force=True)


@contextmanager
def _probe_lock():
    lock = cache.lock(LOCK_KEY, timeout=30, blocking_timeout=0) if hasattr(cache, "lock") else None
    token = uuid.uuid4().hex
    acquired = lock.acquire(blocking=False) if lock else cache.add(LOCK_KEY, token, timeout=30)
    try:
        yield acquired
    finally:
        if acquired and lock:
            with suppress(Exception):
                lock.release()
        elif acquired and cache.get(LOCK_KEY) == token:
            cache.delete(LOCK_KEY)


def inventory(*, force=False):
    """Cache the host-wide probe and coalesce concurrent processes using Redis."""
    try:
        cached = cache.get(CACHE_KEY)
        if cached is not None and not force:
            return cached
        with _probe_lock() as acquired:
            if not acquired:
                return _result("checking", "probe_in_progress")
            # A competing request may have filled the cache before we obtained the lock.
            cached = cache.get(CACHE_KEY)
            result = cached if cached is not None and not force else _probe()
            cache.set(CACHE_KEY, result, timeout=30)
            return result
    except Exception:
        return _result("error", "probe_unavailable")


def require_device(device_id, *, client=None):
    """Reject missing devices, and reject runtimes that expose a different GPU."""
    if not GPU_UUID.fullmatch(device_id or ""):
        raise ValidationError({"local_gpu_id": "Select an available NVIDIA GPU."})
    try:
        with _probe_lock() as acquired:
            if not acquired:
                raise ServiceUnavailable("GPU verification is in progress. Please try again.")
            result = _probe(device_id, client=client)
    except ServiceUnavailable:
        raise
    except Exception as exc:
        raise ServiceUnavailable("Unable to verify the local GPU. Please try again.") from exc
    if result["status"] == "error":
        raise ServiceUnavailable("Unable to verify the local GPU. Please try again.")
    if result["status"] != "available":
        raise ValidationError({"local_gpu_id": "The selected NVIDIA GPU is unavailable or cannot be isolated."})
    return result["devices"][0]


def device_metrics(device_id):
    """Read whole-device usage without trusting the training container."""
    if not GPU_UUID.fullmatch(device_id or ""):
        return None
    try:
        with _probe_lock() as acquired:
            if not acquired:
                return None
            result = _probe(device_id, metrics=True)
        return result["devices"][0] if result["status"] == "available" else None
    except Exception:
        return None
