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
    """Verify RedisQueue HA (2 nodes + 3 Sentinels quorum 2) and RedisCache (standalone 1 replica)."""
    errors: list[str] = []
    app = context.application("mlops-prod-addon-redis-operator")
    source = (app.get("spec") or {}).get("source") or {}
    if (source.get("chart"), str(source.get("targetRevision"))) != ("redis-operator", "0.26.0"):
        errors.append("Redis Operator must use pinned chart redis-operator@0.26.0")

    rendered = context.render("k8s/platform/redis")
    queue_replication = find_resource(rendered, "RedisReplication", "redis-queue-ha")
    queue_sentinel = find_resource(rendered, "RedisSentinel", "redis-queue-ha")
    cache_redis = find_resource(rendered, "Redis", "redis-cache")

    if not queue_replication:
        errors.append("k8s/platform/redis must render RedisReplication redis-queue-ha")
    if not queue_sentinel:
        errors.append("k8s/platform/redis must render RedisSentinel redis-queue-ha")
    if not cache_redis:
        errors.append("k8s/platform/redis must render standalone Redis redis-cache")

    rep_spec = (queue_replication or {}).get("spec") or {}
    sen_spec = (queue_sentinel or {}).get("spec") or {}
    cache_spec = (cache_redis or {}).get("spec") or {}

    if rep_spec.get("clusterSize") != 2 or rep_spec.get("nodeSelector") != {"workload-type": "worker"}:
        errors.append("RedisReplication redis-queue-ha must run exactly two Redis Pods on static workers")
    redis_secret = ((rep_spec.get("kubernetesConfig") or {}).get("redisSecret") or {})
    sentinel_secret = ((sen_spec.get("kubernetesConfig") or {}).get("redisSecret") or {})
    if redis_secret != {"name": "redis-ha-secret", "key": "REDIS_PASSWORD"}:
        errors.append("RedisReplication must use the Redis password Secret key")
    if sentinel_secret != {"name": "redis-ha-secret", "key": "REDIS_SENTINEL_PASSWORD"}:
        errors.append("RedisSentinel must use its separate password Secret key")
    if ((rep_spec.get("pdb") or {}).get("minAvailable")) != 1:
        errors.append("RedisReplication PDB must keep one Redis Pod available")

    config = sen_spec.get("redisSentinelConfig") or {}
    if sen_spec.get("clusterSize") != 3 or config.get("quorum") != "2":
        errors.append("RedisSentinel must run three Pods with quorum two")
    if config.get("redisReplicationName") != "redis-queue-ha" or config.get("masterGroupName") != "redis-queue-master":
        errors.append("RedisSentinel must monitor the declared redis-queue-ha master set")

    cache_secret = ((cache_spec.get("kubernetesConfig") or {}).get("redisSecret") or {})
    if cache_secret != {"name": "redis-ha-secret", "key": "REDIS_PASSWORD"}:
        errors.append("Standalone Redis cache must use the Redis password Secret key")

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

