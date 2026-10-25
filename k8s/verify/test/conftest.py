"""Fixtures and connection safety for online live cluster tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from kubernetes import client, config


def _try_load_kubeconfig() -> bool:
    # 1. Environment variable
    if os.environ.get("KUBECONFIG") and Path(os.environ["KUBECONFIG"]).is_file():
        try:
            config.load_kube_config(config_file=os.environ["KUBECONFIG"])
            return True
        except Exception:
            pass

    # 2. Default ~/.kube/config
    default_config = Path.home() / ".kube" / "config"
    if default_config.is_file():
        try:
            config.load_kube_config(config_file=str(default_config))
            return True
        except Exception:
            pass

    # 3. K3s default location on Linux
    k3s_default = Path("/etc/rancher/k3s/k3s.yaml")
    if k3s_default.is_file():
        try:
            config.load_kube_config(config_file=str(k3s_default))
            return True
        except Exception:
            pass

    # 4. In-cluster ServiceAccount
    try:
        config.load_incluster_config()
        return True
    except Exception:
        pass

    return False


@pytest.fixture(scope="session")
def cluster_connection() -> client.ApiClient:
    """Session fixture that verifies live cluster connectivity, or skips tests gracefully."""
    loaded = _try_load_kubeconfig()
    if not loaded:
        pytest.skip(
            "No valid kubeconfig found. Skipping live cluster tests.",
            allow_module_level=True,
        )

    api_client = client.ApiClient()
    api_client.configuration.client_side_validation = False
    core = client.CoreV1Api(api_client)
    try:
        core.get_api_resources(_request_timeout=3)
    except Exception as exc:
        pytest.skip(
            f"K8s cluster unreachable ({exc}). Skipping live cluster tests.",
            allow_module_level=True,
        )
    return api_client


@pytest.fixture(scope="session")
def k8s_core_api(cluster_connection: client.ApiClient) -> client.CoreV1Api:
    return client.CoreV1Api(cluster_connection)


@pytest.fixture(scope="session")
def k8s_apps_api(cluster_connection: client.ApiClient) -> client.AppsV1Api:
    return client.AppsV1Api(cluster_connection)


@pytest.fixture(scope="session")
def k8s_custom_api(cluster_connection: client.ApiClient) -> client.CustomObjectsApi:
    return client.CustomObjectsApi(cluster_connection)


@pytest.fixture(scope="session")
def k8s_storage_api(cluster_connection: client.ApiClient) -> client.StorageV1Api:
    return client.StorageV1Api(cluster_connection)

