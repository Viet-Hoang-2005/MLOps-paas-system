"""Bounded read-only stats for an explicitly owned local serving container."""

import math

import docker


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value


def parse_stats(stats):
    """CPU in cores and RAM working set in MiB, not host-relative CPU percent."""
    current = stats.get("cpu_stats", {})
    previous = stats.get("precpu_stats", {})
    cpu = None
    totals = [
        _number(current.get("cpu_usage", {}).get("total_usage")),
        _number(previous.get("cpu_usage", {}).get("total_usage")),
        _number(current.get("system_cpu_usage")),
        _number(previous.get("system_cpu_usage")),
    ]
    online = _number(current.get("online_cpus")) or len(current.get("cpu_usage", {}).get("percpu_usage", []))
    if all(value is not None for value in totals) and online > 0:
        used, old_used, system, old_system = totals
        if old_system > 0 and system > old_system and used >= old_used:
            cpu = (used - old_used) / (system - old_system) * online
    memory = stats.get("memory_stats", {})
    usage = _number(memory.get("usage"))
    details = memory.get("stats", {})
    inactive = _number(details.get("total_inactive_file", details.get("inactive_file", 0)))
    ram = max(0, usage - inactive) / 1048576 if usage is not None and inactive is not None else None
    return {"cpu": cpu, "memory": ram}


class DockerMetricsClient:
    def __init__(self, client=None):
        self.client = client

    def sample(self, deployment):
        project = deployment.version.project
        labels = {
            "mlops_project_id": str(project.public_id),
            "mlops_tenant_id": str(project.owner.tenant_id),
            "mlops_version_id": str(deployment.version.public_id),
            "mlops_deployment_id": str(deployment.public_id),
        }
        owned = self.client is None
        client = self.client or docker.from_env(timeout=2)
        try:
            # No container reference from HTTP input, and no scan of all containers.
            container = client.containers.get(f"deploy-{deployment.public_id}")
            if container.status != "running" or any(
                container.labels.get(key) != value for key, value in labels.items()
            ):
                return None
            return parse_stats(container.stats(stream=False))
        finally:
            if owned:
                client.close()
