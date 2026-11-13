"""Live cluster verification: Node health, readiness, and workload labels."""

from __future__ import annotations

import pytest
from kubernetes import client


@pytest.mark.cluster
def test_all_nodes_ready(k8s_core_api: client.CoreV1Api) -> None:
    """Verify that every node in the K3s cluster is in Ready state."""
    nodes = k8s_core_api.list_node().items
    assert len(nodes) > 0, "Cluster must have at least one Node registered."

    not_ready = []
    for node in nodes:
        name = node.metadata.name
        conditions = node.status.conditions or []
        ready_condition = next(
            (c for c in conditions if c.type == "Ready"), None
        )
        if not ready_condition or ready_condition.status != "True":
            not_ready.append(f"Node {name} is not Ready ({ready_condition})")

    assert not not_ready, "\n".join(not_ready)


@pytest.mark.cluster
def test_worker_nodes_labeled(k8s_core_api: client.CoreV1Api) -> None:
    """Verify that worker nodes have the workload-type=worker label."""
    nodes = k8s_core_api.list_node().items
    for node in nodes:
        labels = node.metadata.labels or {}
        # If it's not a control-plane/master node, it must be labeled worker
        is_master = (
            "node-role.kubernetes.io/master" in labels
            or "node-role.kubernetes.io/control-plane" in labels
        )
        if not is_master:
            assert labels.get("workload-type") == "worker", (
                f"Worker node {node.metadata.name} missing label workload-type=worker"
            )

