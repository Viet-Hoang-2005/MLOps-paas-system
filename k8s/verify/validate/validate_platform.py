"""Validate Platform Plane resources: Redis HA, CNPG Postgres, Kyverno supply chain, and Logging."""

from __future__ import annotations

import pytest

from ..utils import (
    STANDARD_APP_LABELS,
    STANDARD_MLOPS_LABELS,
    ValidationContext,
    find_resource,
)


@pytest.mark.validate
def validate_redis_ha_topology(context: ValidationContext) -> None:
    """Verify RedisReplication (2 nodes) and RedisSentinel (3 nodes quorum 2) HA topology."""
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

    config = sentinel.get("redisSentinelConfig") or {}
    if sentinel.get("clusterSize") != 3 or config.get("quorum") != "2":
        errors.append("RedisSentinel must run three Pods with quorum two")
    if config.get("redisReplicationName") != "redis-ha" or config.get("masterGroupName") != "redis-master":
        errors.append("RedisSentinel must monitor the declared RedisReplication master set")

    assert not errors, "\n".join(errors)


@pytest.mark.validate
def validate_postgres_cnpg_cluster(context: ValidationContext) -> None:
    """Verify CloudNativePG Cluster resource for PostgreSQL High Availability."""
    resources = context.render("k8s/platform/postgres")
    cluster = find_resource(resources, "Cluster", "postgresql")
    assert cluster, "k8s/platform/postgres must render Cluster postgresql"
    spec = cluster.get("spec") or {}
    assert spec.get("instances") == 2, "CNPG postgresql must configure 2 instances (Primary + Standby)"
    storage = spec.get("storage") or {}
    assert storage.get("size"), "PostgreSQL storage size must be declared"


@pytest.mark.validate
def validate_supply_chain_security(context: ValidationContext) -> None:
    """Verify Kyverno image verification policy and signer identities."""
    resources = context.render("k8s/cluster/image")
    policy = find_resource(resources, "ClusterPolicy", "verify-platform-images")
    assert policy, "k8s/cluster/image must render ClusterPolicy verify-platform-images"
    spec = policy.get("spec") or {}
    rules = spec.get("rules") or []
    assert rules, "verify-platform-images policy must define rules"
    rule = rules[0]
    verify_images = rule.get("verifyImages") or []
    assert verify_images, "verify-platform-images must specify verifyImages rule"
    attestors = verify_images[0].get("attestors") or []
    assert attestors, "Must configure Cosign keyless attestor"


@pytest.mark.validate
def validate_platform_standard_labels(context: ValidationContext) -> None:
    """Verify standard labels across platform manifests."""
    paths = [
        "k8s/platform/postgres",
        "k8s/platform/redis",
        "k8s/platform/redpanda",
        "k8s/platform/cloudflare",
    ]
    errors: list[str] = []
    for path in paths:
        for resource in context.render(path):
            labels = (resource.get("metadata") or {}).get("labels") or {}
            missing_app = STANDARD_APP_LABELS - set(labels.keys())
            if missing_app:
                name = (resource.get("metadata") or {}).get("name")
                errors.append(f"{path} resource {name} missing app labels: {missing_app}")
            missing_mlops = STANDARD_MLOPS_LABELS - set(labels.keys())
            if missing_mlops:
                name = (resource.get("metadata") or {}).get("name")
                errors.append(f"{path} resource {name} missing mlops labels: {missing_mlops}")
    assert not errors, "\n".join(errors)

