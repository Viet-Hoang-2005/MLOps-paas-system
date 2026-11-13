"""Live cluster verification: Platform services health (Postgres CNPG, Redis HA, Harbor)."""

from __future__ import annotations

import pytest
from kubernetes import client


@pytest.mark.cluster
def test_postgres_ha_cluster_healthy(k8s_custom_api: client.CustomObjectsApi) -> None:
    """Verify that CloudNativePG Postgres cluster has at least 2 ready instances (Primary + Standby)."""
    try:
        clusters = k8s_custom_api.list_namespaced_custom_object(
            group="postgresql.cnpg.io",
            version="v1",
            namespace="mlops-paas-data",
            plural="clusters",
        )
        items = clusters.get("items") or []
        assert items, "No CNPG Cluster found in namespace mlops-paas-data"
        pg_cluster = items[0]
        status = pg_cluster.get("status") or {}
        ready_instances = status.get("readyInstances", 0)
        assert ready_instances >= 2, (
            f"Postgres HA requires at least 2 ready instances, found {ready_instances}"
        )
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            pytest.skip("CNPG CRD not yet installed or not found.")
        raise


@pytest.mark.cluster
def test_redis_pods_running(k8s_core_api: client.CoreV1Api) -> None:
    """Verify that Redis and Sentinel pods are running in mlops-paas-data."""
    pods = k8s_core_api.list_namespaced_pod("mlops-paas-data").items
    redis_pods = [p for p in pods if "redis" in p.metadata.name.lower()]
    assert len(redis_pods) >= 2, (
        f"Expected at least 2 Redis/Sentinel pods in mlops-paas-data, found {len(redis_pods)}"
    )
    for pod in redis_pods:
        assert pod.status.phase == "Running", f"Redis pod {pod.metadata.name} not Running"

