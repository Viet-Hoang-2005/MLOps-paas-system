"""Live cluster verification: Workloads Deployments health and replicas readiness."""

from __future__ import annotations

import pytest
from kubernetes import client


@pytest.mark.cluster
@pytest.mark.parametrize(
    "deployment_name",
    [
        "mlops-paas-control-plane",
        "mlops-paas-celery-worker",
        "mlops-paas-celery-beat",
        "mlops-paas-consumer",
        "mlops-paas-model-server",
    ],
)
def test_workload_deployment_ready(
    k8s_apps_api: client.AppsV1Api, deployment_name: str
) -> None:
    """Verify that every workload deployment has at least one Ready replica."""
    try:
        deployment = k8s_apps_api.read_namespaced_deployment(
            name=deployment_name, namespace="mlops-paas-core"
        )
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            pytest.fail(f"Workload deployment {deployment_name} not found in mlops-paas-core")
        raise

    status = deployment.status
    ready = status.ready_replicas or 0
    assert ready >= 1, (
        f"Deployment {deployment_name} has {ready} ready replicas (desired: {deployment.spec.replicas})"
    )

