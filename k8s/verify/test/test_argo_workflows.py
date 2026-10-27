"""Live cluster verification for Argo Workflows core operational tasks."""

from __future__ import annotations

import pytest
from kubernetes import client

from ..utils import ARGO_WORKFLOW_TEMPLATES


@pytest.mark.cluster
def test_argo_crds_established(k8s_custom_api: client.CustomObjectsApi) -> None:
    """Verify Argo Workflows CustomResourceDefinitions are established on the cluster."""
    try:
        crds = k8s_custom_api.list_cluster_custom_object(
            group="apiextensions.k8s.io",
            version="v1",
            plural="customresourcedefinitions",
        )
        crd_names = {
            item.get("metadata", {}).get("name")
            for item in crds.get("items", [])
        }
    except client.exceptions.ApiException as exc:
        pytest.fail(f"Failed to query CRDs: {exc}")

    expected_crds = {
        "workflowtemplates.argoproj.io",
        "workflows.argoproj.io",
    }
    missing = expected_crds - crd_names
    assert not missing, f"Missing Argo Workflows CRDs: {missing}"


@pytest.mark.cluster
@pytest.mark.parametrize("template_name", list(ARGO_WORKFLOW_TEMPLATES.values()))
def test_argo_workflow_templates_exist(
    k8s_custom_api: client.CustomObjectsApi, template_name: str
) -> None:
    """Verify that all 9 operational WorkflowTemplates exist in mlops-paas-execution."""
    try:
        template = k8s_custom_api.get_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace="mlops-paas-execution",
            plural="workflowtemplates",
            name=template_name,
        )
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            pytest.fail(
                f"WorkflowTemplate '{template_name}' not found in namespace mlops-paas-execution"
            )
        raise

    metadata = template.get("metadata", {})
    assert metadata.get("name") == template_name
    assert template.get("apiVersion") == "argoproj.io/v1alpha1"
    assert template.get("kind") == "WorkflowTemplate"
    assert "spec" in template


@pytest.mark.cluster
def test_argo_service_accounts_exist(k8s_core_api: client.CoreV1Api) -> None:
    """Verify all 5 execution ServiceAccounts exist in mlops-paas-execution."""
    expected_sas = {
        "argo-workflow-basic-sa",
        "argo-workflow-deploy-sa",
        "argo-workflow-delete-sa",
        "argo-workflow-training-sa",
        "argo-job-operations-sa",
    }
    try:
        sas = k8s_core_api.list_namespaced_service_account(namespace="mlops-paas-execution")
    except client.exceptions.ApiException as exc:
        pytest.fail(f"Failed to list ServiceAccounts in mlops-paas-execution: {exc}")

    actual_names = {sa.metadata.name for sa in sas.items}
    missing = expected_sas - actual_names
    assert not missing, f"Missing ServiceAccounts in mlops-paas-execution: {missing}"


@pytest.mark.cluster
def test_argo_job_operations_configmap(k8s_core_api: client.CoreV1Api) -> None:
    """Verify argo-job-operations ConfigMap exists and contains job_ops.py."""
    try:
        cm = k8s_core_api.read_namespaced_config_map(
            name="argo-job-operations",
            namespace="mlops-paas-execution",
        )
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            pytest.fail("ConfigMap argo-job-operations not found in mlops-paas-execution")
        raise

    data = cm.data or {}
    assert "job_ops.py" in data, "argo-job-operations ConfigMap must contain job_ops.py"
    assert len(data["job_ops.py"]) > 200, "job_ops.py content should not be empty"


@pytest.mark.cluster
def test_argo_execution_config_configmap(k8s_core_api: client.CoreV1Api) -> None:
    """Verify mlops-paas-execution-config ConfigMap exists with standard keys."""
    try:
        cm = k8s_core_api.read_namespaced_config_map(
            name="mlops-paas-execution-config",
            namespace="mlops-paas-execution",
        )
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            pytest.fail("ConfigMap mlops-paas-execution-config not found in mlops-paas-execution")
        raise

    data = cm.data or {}
    assert "LOG_FORMAT" in data
    assert "HARBOR_REGISTRY_URL" in data


@pytest.mark.cluster
def test_argo_rbac_bindings(k8s_rbac_api: client.RbacAuthorizationV1Api) -> None:
    """Verify RoleBindings for workflow execution across execution, serving, and training planes."""
    try:
        exec_rbs = k8s_rbac_api.list_namespaced_role_binding(namespace="mlops-paas-execution")
        serving_rbs = k8s_rbac_api.list_namespaced_role_binding(namespace="mlops-paas-serving")
        training_rbs = k8s_rbac_api.list_namespaced_role_binding(namespace="mlops-paas-training")
    except client.exceptions.ApiException as exc:
        pytest.fail(f"Failed to query RoleBindings: {exc}")

    exec_names = {rb.metadata.name for rb in exec_rbs.items}
    serving_names = {rb.metadata.name for rb in serving_rbs.items}
    training_names = {rb.metadata.name for rb in training_rbs.items}

    assert "argo-workflow-executor" in exec_names
    assert "argo-job-operations" in exec_names
    assert "argo-workflow-deploy" in serving_names
    assert "argo-workflow-delete" in serving_names
    assert "argo-training-job-role-binding" in training_names


@pytest.mark.cluster
def test_argo_network_policies_applied(
    k8s_networking_api: client.NetworkingV1Api,
) -> None:
    """Verify NetworkPolicies are applied in mlops-paas-execution."""
    try:
        netpols = k8s_networking_api.list_namespaced_network_policy(
            namespace="mlops-paas-execution"
        )
    except client.exceptions.ApiException as exc:
        pytest.fail(f"Failed to query NetworkPolicies: {exc}")

    names = {np.metadata.name for np in netpols.items}
    expected = {
        "np-mlops-paas-model-packager",
        "np-mlops-paas-evidently",
        "np-mlops-paas-job-operations",
        "default-deny-all-ingress-execution",
    }
    missing = expected - names
    assert not missing, f"Missing NetworkPolicies in mlops-paas-execution: {missing}"

