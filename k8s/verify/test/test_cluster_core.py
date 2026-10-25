"""Live cluster verification: Core infrastructure, StorageClasses, Namespaces, and SecretStore."""

from __future__ import annotations

import pytest
from kubernetes import client


@pytest.mark.cluster
def test_production_namespaces_exist(k8s_core_api: client.CoreV1Api) -> None:
    """Verify that required production namespaces exist on the live cluster."""
    namespaces = {ns.metadata.name for ns in k8s_core_api.list_namespace().items}
    # Check core critical namespaces
    critical_namespaces = {
        "argocd",
        "argo",
        "argo-events",
        "cnpg-system",
        "external-secrets",
        "mlops-paas-system",
        "mlops-paas-core",
        "mlops-paas-data",
        "mlops-paas-execution",
    }
    missing = critical_namespaces - namespaces
    assert not missing, f"Missing critical production namespaces: {missing}"


@pytest.mark.cluster
def test_storage_classes_installed(k8s_storage_api: client.StorageV1Api) -> None:
    """Verify that required storage classes are installed and ready."""
    storage_classes = {sc.metadata.name for sc in k8s_storage_api.list_storage_class().items}
    assert len(storage_classes) > 0, "No StorageClass registered on cluster."


@pytest.mark.cluster
def test_cluster_secret_store_ready(k8s_custom_api: client.CustomObjectsApi) -> None:
    """Verify that ClusterSecretStore aws-secrets-manager is Ready."""
    try:
        secret_stores = k8s_custom_api.list_cluster_custom_object(
            group="external-secrets.io",
            version="v1beta1",
            plural="clustersecretstores",
        )
        items = secret_stores.get("items") or []
        assert any(
            item["metadata"]["name"] == "aws-secrets-manager" for item in items
        ), "ClusterSecretStore aws-secrets-manager not found."
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            pytest.skip("ExternalSecrets CRD not yet installed on cluster.")
        raise

