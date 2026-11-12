"""Docker capacity discovery and durable admission for local training."""

import math
import re
import time
import uuid
from contextlib import contextmanager, suppress
from datetime import datetime, timezone

from django.conf import settings
from django.core.cache import cache
from django.db.models import Sum
from django.utils import timezone as django_timezone

from apps.training.models import LocalTrainingPool, LocalTrainingReservation, TrainingJob
from common.api.exceptions import Conflict, ServiceUnavailable
from infrastructure.docker import DockerClient

IMAGE = "mlops-paas-training-runner:latest"
CACHE_KEY = "training:local-resources:capacity:v1"
LOCK_KEY = "training:local-resources:dispatch:v1"
MIB = 1024 * 1024


class LocalTrainingCapacityExceeded(Conflict):
    default_code = "local_training_capacity_exceeded"


def profiles(cpus, memory_mib):
    """Compute the advertised limits without exceeding the reserved host budget."""
    if cpus < 1 or memory_mib < 1:
        return []
    cpu = max(1, min(8, cpus * 3 // 4))
    memory = min(memory_mib * 3 // 4, memory_mib - 1536) // 512 * 512
    if memory < 1024:
        return []
    candidates = [
        {"id": "large", "vcpu": cpu, "memory_mb": memory},
        {"id": "medium", "vcpu": max(1, cpu // 2), "memory_mb": max(1024, (memory // 2) // 256 * 256)},
        {"id": "small", "vcpu": max(1, cpu // 4), "memory_mb": max(512, (memory // 4) // 256 * 256)},
    ]
    seen, result = set(), []
    for item in candidates:
        key = item["vcpu"], item["memory_mb"]
        if key not in seen:
            result.append(item)
            seen.add(key)
    return list(reversed(result))


def _discover():
    client = None
    try:
        client = DockerClient(timeout=3).client
        info = client.info()
        cpu, memory = int(info["NCPU"]), int(info["MemTotal"]) // MIB
        daemon_id = info["ID"]
        if (
            not isinstance(daemon_id, str)
            or not daemon_id
            or len(daemon_id) > 128
            or not info.get("MemoryLimit")
            or not info.get("CpuCfsQuota")
        ):
            raise ValueError("Unsupported Docker resource limits")
        choices = profiles(cpu, memory)
        return {
            "status": "available" if choices else "unavailable",
            "reason": "" if choices else "insufficient_capacity",
            "daemon_id": daemon_id,
            "total_vcpu": cpu,
            "total_memory_mb": memory,
            "cpu_profiles": choices,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception:
        return {
            "status": "error",
            "reason": "docker_unavailable",
            "cpu_profiles": [],
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        if client is not None:
            with suppress(Exception):
                client.close()


def capacity(*, force=False):
    try:
        cached = cache.get(CACHE_KEY)
        if cached is not None and not force:
            return cached
        # Cache.add works across processes when the configured cache is Redis.
        token = uuid.uuid4().hex
        key = CACHE_KEY + ":lock"
        if not cache.add(key, token, timeout=15):
            return (
                cached
                if cached is not None and not force
                else {"status": "checking", "reason": "checking", "cpu_profiles": []}
            )
        try:
            result = _discover()
            cache.set(CACHE_KEY, result, timeout=30)
            return result
        finally:
            if cache.get(key) == token:
                cache.delete(key)
    except Exception:
        return {"status": "error", "reason": "cache_unavailable", "cpu_profiles": []}


def require_capacity(*, force=False):
    result = capacity(force=force)
    if result.get("status") != "available":
        raise ServiceUnavailable("Local Docker training capacity is unavailable. Please check Docker and try again.")
    if force:
        _check_unmanaged(result["daemon_id"])
    return result


def _check_unmanaged(daemon_id):
    """Do not ignore training containers created before reservations existed."""
    client = None
    try:
        client = DockerClient(timeout=3).client
        known = {
            str(job_id)
            for job_id in LocalTrainingReservation.objects.filter(pool__daemon_id=daemon_id, active=True).values_list(
                "job_id", flat=True
            )
        }
        for container in client.containers.list(all=True):
            if not (container.name or "").startswith("training-"):
                continue
            state = (container.attrs.get("State") or {}).get("Status")
            if state not in {"created", "running", "restarting", "paused"}:
                continue
            labels = (container.attrs.get("Config") or {}).get("Labels") or {}
            job_id = labels.get("mlops_training_id")
            managed_name = container.name == f"training-{job_id}" or (
                labels.get("mlops_role") == "input" and container.name == f"training-input-{job_id}"
            )
            if job_id not in known or not managed_name:
                raise ServiceUnavailable(
                    "An existing training container has no capacity reservation. Stop or reconcile it first."
                )
    except ServiceUnavailable:
        raise
    except Exception as exc:
        raise ServiceUnavailable("Unable to verify existing Docker training containers.") from exc
    finally:
        if client is not None:
            with suppress(Exception):
                client.close()


def totals(daemon_id):
    sums = LocalTrainingReservation.objects.filter(pool__daemon_id=daemon_id, active=True).aggregate(
        cpu=Sum("vcpu"), memory=Sum("memory_mb")
    )
    return sums["cpu"] or 0, sums["memory"] or 0


def public_capacity(snapshot):
    result = {key: value for key, value in snapshot.items() if key not in {"daemon_id", "cpu_profiles"}}
    if snapshot.get("status") == "available":
        large = next(p for p in snapshot["cpu_profiles"] if p["id"] == "large")
        cpu, memory = totals(snapshot["daemon_id"])
        result.update(
            budget_vcpu=large["vcpu"],
            budget_memory_mb=large["memory_mb"],
            reserved_vcpu=cpu,
            reserved_memory_mb=memory,
            available_vcpu=max(0, large["vcpu"] - cpu),
            available_memory_mb=max(0, large["memory_mb"] - memory),
        )
    return result


def reserve(job, snapshot):
    """Called in the submit transaction. The pool row serializes all tenants."""
    if not settings.TRAINING_EXECUTION_WATCH_ENABLED:
        raise ServiceUnavailable("Local training requires execution monitoring.")
    pool, _ = LocalTrainingPool.objects.get_or_create(daemon_id=snapshot["daemon_id"])
    pool = LocalTrainingPool.objects.select_for_update().get(pk=pool.pk)
    large = next(p for p in snapshot["cpu_profiles"] if p["id"] == "large")
    cpu, memory = totals(pool.daemon_id)
    if cpu + job.vcpu > large["vcpu"] or memory + job.memory_mb > large["memory_mb"]:
        raise LocalTrainingCapacityExceeded(
            {
                "detail": "Insufficient local training capacity.",
                "available_vcpu": max(0, large["vcpu"] - cpu),
                "available_memory_mb": max(0, large["memory_mb"] - memory),
            }
        )
    LocalTrainingReservation.objects.create(pool=pool, job_id=job.public_id, vcpu=job.vcpu, memory_mb=job.memory_mb)


def release(job):
    LocalTrainingReservation.objects.filter(job_id=job.public_id, active=True).update(
        active=False, stopped_at=django_timezone.now()
    )


def _memory_available(client, expected_memory_mb):
    container = None
    name = "mlops-local-memory-probe-" + uuid.uuid4().hex
    try:
        for stale in client.containers.list(all=True, filters={"label": "mlops_paas.memory_probe=true"}):
            labels = (stale.attrs.get("Config") or {}).get("Labels") or {}
            expires = labels.get("mlops_paas.memory_probe_expires", "")
            if (
                re.fullmatch(r"mlops-local-memory-probe-[0-9a-f]{32}", stale.name or "")
                and str(expires).isdigit()
                and int(expires) < time.time()
            ):
                with suppress(Exception):
                    stale.remove(force=True)
        client.images.get(IMAGE)
        container = client.containers.create(
            IMAGE,
            name=name,
            entrypoint="cat",
            command=["/proc/meminfo"],
            network_disabled=True,
            user="10001:10001",
            mem_limit="64m",
            nano_cpus=250_000_000,
            pids_limit=32,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            detach=True,
            labels={"mlops_paas.memory_probe": "true", "mlops_paas.memory_probe_expires": str(int(time.time()) + 120)},
        )
        container.start()
        if container.wait(timeout=5).get("StatusCode") != 0:
            raise ValueError("Memory probe failed")
        output = container.logs(stdout=True, stderr=False).decode("ascii", errors="replace")
        match = re.search(r"^MemAvailable:\s+(\d+)\s+kB\s*$", output, re.MULTILINE)
        total = re.search(r"^MemTotal:\s+(\d+)\s+kB\s*$", output, re.MULTILINE)
        if not match or not total or abs(int(total.group(1)) // 1024 - expected_memory_mb) > 32:
            raise ValueError("MemAvailable missing")
        return int(match.group(1)) // 1024
    finally:
        if container is not None:
            with suppress(Exception):
                container.remove(force=True)
        else:
            with suppress(Exception):
                client.containers.get(name).remove(force=True)


def _outstanding_memory(client, daemon_id, current_job):
    """Account for unused reservations without charging active working sets twice."""
    from infrastructure.docker_metrics import parse_stats
    from infrastructure.execution.job_containers import labels_for

    total = 0
    reservations = LocalTrainingReservation.objects.filter(pool__daemon_id=daemon_id, active=True)
    for reservation in reservations:
        unused = reservation.memory_mb
        if reservation.job_id != current_job.public_id:
            try:
                job = TrainingJob.objects.select_related("project__owner").get(public_id=reservation.job_id)
                container = client.containers.get(f"training-{job.public_id}")
                container.reload()
                labels = (container.attrs.get("Config") or {}).get("Labels") or {}
                if (
                    job.external_job_id
                    and container.id == job.external_job_id
                    and (container.attrs.get("State") or {}).get("Status") == "running"
                    and all(labels.get(key) == value for key, value in labels_for(job, "training").items())
                ):
                    used = parse_stats(container.stats(stream=False))["memory"]
                    if used is not None and math.isfinite(used) and used >= 0:
                        unused = max(0, reservation.memory_mb - min(reservation.memory_mb, used))
            except Exception:
                pass  # Missing or unverifiable usage is charged at the full limit.
        total += unused
    return math.ceil(total)


@contextmanager
def dispatch_guard(job, client):
    """Serialize preflight and container creation; a cache failure is fail-closed."""
    lock = None
    try:
        lock = (
            cache.lock(LOCK_KEY, timeout=max(120, settings.EXECUTION_CHECK_LEASE_SECONDS + 30), blocking_timeout=0)
            if hasattr(cache, "lock")
            else None
        )
        if lock is None or not lock.acquire(blocking=False):
            raise ServiceUnavailable("Local training dispatch is busy. Please retry.")
        snapshot = require_capacity(force=True)
        reservation = LocalTrainingReservation.objects.filter(
            job_id=job.public_id, active=True, pool__daemon_id=snapshot["daemon_id"]
        ).first()
        if not reservation or (reservation.vcpu, reservation.memory_mb) != (job.vcpu, job.memory_mb):
            raise ServiceUnavailable("Local training reservation is unavailable.")
        large = next(p for p in snapshot["cpu_profiles"] if p["id"] == "large")
        cpu, memory = totals(snapshot["daemon_id"])
        if cpu > large["vcpu"] or memory > large["memory_mb"]:
            raise ServiceUnavailable("Docker capacity changed; waiting for resources.")
        try:
            available = _memory_available(client, snapshot["total_memory_mb"])
            outstanding = _outstanding_memory(client, snapshot["daemon_id"], job)
        except Exception as exc:
            raise ServiceUnavailable("Unable to check available Docker memory.") from exc
        if available < outstanding:
            raise ServiceUnavailable("Insufficient available Docker memory; waiting for resources.")
        if not lock.owned():
            raise ServiceUnavailable("Local dispatch lock expired.")
        yield
    finally:
        if lock is not None:
            with suppress(Exception):
                if lock.owned():
                    lock.release()
