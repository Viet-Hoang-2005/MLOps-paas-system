"""Live cluster verification: Argo CD GitOps Applications sync and health states."""

from __future__ import annotations

import pytest
from kubernetes import client


@pytest.mark.cluster
def test_argocd_root_application_healthy(k8s_custom_api: client.CustomObjectsApi) -> None:
    """Verify that root App-of-apps 'mlops-paas-system' is Synced and Healthy."""
    try:
        root_app = k8s_custom_api.get_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace="argocd",
            plural="applications",
            name="mlops-paas-system",
        )
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            pytest.fail("Root Argo CD Application 'mlops-paas-system' not found in argocd namespace.")
        raise

    status = root_app.get("status") or {}
    sync_status = (status.get("sync") or {}).get("status")
    health_status = (status.get("health") or {}).get("status")

    assert sync_status == "Synced", f"Root Application sync status is '{sync_status}', expected 'Synced'"
    assert health_status == "Healthy", f"Root Application health status is '{health_status}', expected 'Healthy'"


@pytest.mark.cluster
def test_all_child_applications_synced_and_healthy(
    k8s_custom_api: client.CustomObjectsApi,
) -> None:
    """Verify that all 35 child Applications in Argo CD are Synced and Healthy."""
    try:
        apps = k8s_custom_api.list_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace="argocd",
            plural="applications",
        )
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            pytest.skip("Argo CD Applications CRD not installed.")
        raise

    items = apps.get("items") or []
    # Exclude root app itself
    child_apps = [app for app in items if app["metadata"]["name"] != "mlops-paas-system"]

    not_synced = []
    not_healthy = []

    for app in child_apps:
        name = app["metadata"]["name"]
        status = app.get("status") or {}
        sync = (status.get("sync") or {}).get("status")
        health = (status.get("health") or {}).get("status")

        if sync != "Synced":
            not_synced.append(f"{name}: sync={sync}")
        if health != "Healthy":
            not_healthy.append(f"{name}: health={health}")

    assert not not_synced, f"Unsynced child Applications:\n" + "\n".join(not_synced)
    assert not not_healthy, f"Unhealthy child Applications:\n" + "\n".join(not_healthy)

