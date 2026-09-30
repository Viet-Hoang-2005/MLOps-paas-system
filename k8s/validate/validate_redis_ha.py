"""Validate the three-node Redis/Sentinel production topology."""

from __future__ import annotations

from .common import ValidationContext, run_standalone


def validate(context: ValidationContext) -> list[str]:
    errors: list[str] = []
    app = context.application("mlops-prod-addon-redis-operator")
    source = (app.get("spec") or {}).get("source") or {}
    if (source.get("chart"), str(source.get("targetRevision"))) != ("redis-operator", "0.26.0"):
        errors.append("Redis Operator must use pinned chart redis-operator@0.26.0")

    rendered = context.render("k8s/platform/redis")
    resources = {
        resource.get("kind"): resource
        for resource in rendered
        if resource.get("kind") in {"RedisReplication", "RedisSentinel"}
    }
    replication = (resources.get("RedisReplication") or {}).get("spec") or {}
    sentinel = (resources.get("RedisSentinel") or {}).get("spec") or {}
    if replication.get("clusterSize") != 2 or replication.get("nodeSelector") != {"workload-type": "worker"}:
        errors.append("RedisReplication must run exactly two Redis Pods on static workers")
    redis_secret = ((replication.get("kubernetesConfig") or {}).get("redisSecret") or {})
    sentinel_secret = ((sentinel.get("kubernetesConfig") or {}).get("redisSecret") or {})
    if redis_secret != {"name": "redis-ha-secret", "key": "REDIS_PASSWORD"}:
        errors.append("RedisReplication must use the Redis password Secret key")
    if sentinel_secret != {"name": "redis-ha-secret", "key": "REDIS_SENTINEL_PASSWORD"}:
        errors.append("RedisSentinel must use its separate password Secret key")
    if ((replication.get("pdb") or {}).get("minAvailable")) != 1:
        errors.append("RedisReplication PDB must keep one Redis Pod available")
    redis_affinity = ((replication.get("affinity") or {}).get("podAntiAffinity") or {}).get("requiredDuringSchedulingIgnoredDuringExecution") or []
    if not redis_affinity or redis_affinity[0].get("topologyKey") != "kubernetes.io/hostname":
        errors.append("Redis Pods require hostname anti-affinity")
    claim = (((replication.get("storage") or {}).get("volumeClaimTemplate") or {}).get("spec") or {})
    if claim.get("storageClassName") != "ebs-gp3" or (((claim.get("resources") or {}).get("requests") or {}).get("storage")) != "5Gi":
        errors.append("Each Redis Pod requires a 5 GiB ebs-gp3 PVC")

    config = sentinel.get("redisSentinelConfig") or {}
    if sentinel.get("clusterSize") != 3 or config.get("quorum") != "2":
        errors.append("RedisSentinel must run three Pods with quorum two")
    if config.get("redisReplicationName") != "mlops-paas-redis-ha" or config.get("masterGroupName") != "mlops-paas-redis":
        errors.append("RedisSentinel must monitor the declared RedisReplication master set")
    node_terms = ((((sentinel.get("affinity") or {}).get("nodeAffinity") or {}).get("requiredDuringSchedulingIgnoredDuringExecution") or {}).get("nodeSelectorTerms") or [])
    if not node_terms or not any(
        expression.get("key") == "workload-type" and set(expression.get("values") or []) == {"worker", "control-plane"}
        for term in node_terms for expression in term.get("matchExpressions") or []
    ):
        errors.append("Sentinel must be restricted to workers and the static control-plane")
    anti_affinity = ((sentinel.get("affinity") or {}).get("podAntiAffinity") or {}).get("requiredDuringSchedulingIgnoredDuringExecution") or []
    if not anti_affinity or anti_affinity[0].get("topologyKey") != "kubernetes.io/hostname":
        errors.append("Sentinel Pods require hostname anti-affinity")
    if ((sentinel.get("pdb") or {}).get("minAvailable")) != 2:
        errors.append("Sentinel PDB must retain quorum during voluntary disruption")
    if not any(
        item.get("key") == "node-role.kubernetes.io/control-plane"
        and item.get("value") == "true"
        and item.get("effect") == "NoSchedule"
        for item in sentinel.get("tolerations") or []
    ):
        errors.append("Only Sentinel must tolerate the control-plane taint")
    if replication.get("tolerations"):
        errors.append("Redis Pods must not tolerate control-plane/training taints")
    config_map = next((resource for resource in rendered if resource.get("kind") == "ConfigMap"), {})
    config_text = ((config_map.get("data") or {}).get("redis-additional.conf") or "")
    if not all(item in config_text for item in ("appendonly yes", "appendfsync everysec", "maxmemory-policy noeviction")):
        errors.append("Redis must enable AOF everysec and noeviction")
    external_secret = next((resource for resource in rendered if resource.get("kind") == "ExternalSecret"), {})
    secret_keys = {item.get("secretKey") for item in (external_secret.get("spec") or {}).get("data") or []}
    if secret_keys != {"REDIS_PASSWORD", "REDIS_SENTINEL_PASSWORD"}:
        errors.append("Redis ExternalSecret must provide only Redis and Sentinel credentials")
    return errors


if __name__ == "__main__":  # pragma: no cover - CLI boundary
    raise SystemExit(run_standalone("redis-ha", validate))
