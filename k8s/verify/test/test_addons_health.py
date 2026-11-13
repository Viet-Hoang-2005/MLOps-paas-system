"""Live cluster verification: Addons health and operator Pod readiness."""

from __future__ import annotations

import pytest
from kubernetes import client


@pytest.mark.cluster
@pytest.mark.parametrize(
    "namespace,expected_prefix",
    [
        ("argocd", "argocd-server"),
        ("argocd", "argocd-repo-server"),
        ("argocd", "argocd-application-controller"),
        ("argo", "argo-server"),
        ("cnpg-system", "cnpg-controller-manager"),
    ],
)
def test_addon_core_pods_running(
    k8s_core_api: client.CoreV1Api, namespace: str, expected_prefix: str
) -> None:
    """Verify that core Add-on pods are Running on the cluster."""
    pods = k8s_core_api.list_namespaced_pod(namespace).items
    matching_pods = [
        pod for pod in pods
        if pod.metadata.name.startswith(expected_prefix)
    ]
    assert matching_pods, f"No pod with prefix '{expected_prefix}' found in {namespace}"

    for pod in matching_pods:
        phase = pod.status.phase
        assert phase in {"Running", "Succeeded"}, (
            f"Pod {pod.metadata.name} in {namespace} is in phase {phase}"
        )

