"""Validate Cluster Plane resources: Karpenter capacity, secret-store, and storage."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ..utils import (
    EXTERNAL_SECRET_OWNERS,
    LEGACY_SHARED_SECRET_TARGETS,
    STANDARD_APP_LABELS,
    ValidationContext,
    find_resource,
    resource_namespace,
)


def requirement_values(pool: dict[str, Any], key: str) -> set[str]:
    for requirement in (
        ((pool.get("spec") or {}).get("template") or {}).get("spec") or {}
    ).get("requirements") or []:
        if requirement.get("key") == key:
            return set(requirement.get("values") or [])
    return set()


def check_nodeclass(nodeclass: dict[str, Any], name: str) -> list[str]:
    errors: list[str] = []
    spec = nodeclass.get("spec") or {}
    options = spec.get("metadataOptions") or {}
    expected_options = {
        "httpEndpoint": "enabled",
        "httpProtocolIPv6": "disabled",
        "httpPutResponseHopLimit": 1,
        "httpTokens": "required",
    }
    if options != expected_options:
        errors.append(f"EC2NodeClass {name} must require IMDSv2 with hop limit 1")
    if (
        spec.get("amiFamily") != "Custom"
        or spec.get("instanceProfile") != "mlops-karpenter-node-profile"
    ):
        errors.append(
            f"EC2NodeClass {name} must use the production custom AMI and instance profile"
        )
    user_data = spec.get("userData") or ""
    if (
        "--secret-id mlops/k3s-agent-token" not in user_data
        or "k3s-api.internal.mlops-nids-nt114.id.vn:6443" not in user_data
    ):
        errors.append(
            f"EC2NodeClass {name} must retrieve join token from Secrets Manager and join private DNS"
        )
    if 'K3S_TOKEN="K10' in user_data or "K3S_TOKEN='K10" in user_data:
        errors.append(f"EC2NodeClass {name} must not embed a K3s token in Git")
    return errors


def check_pool(
    pool: dict[str, Any], name: str, nodeclass: str, instances: set[str], *, gpu: bool
) -> list[str]:
    errors: list[str] = []
    spec = pool.get("spec") or {}
    template = spec.get("template") or {}
    template_spec = template.get("spec") or {}
    if (spec.get("limits") or {}).get("nodes") != 1:
        errors.append(f"NodePool {name} must limit capacity to one node")
    if requirement_values(pool, "karpenter.sh/capacity-type") != {"spot", "on-demand"}:
        errors.append(f"NodePool {name} must permit Spot with On-Demand fallback")
    if requirement_values(pool, "node.kubernetes.io/instance-type") != instances:
        errors.append(f"NodePool {name} must use its production instance allowlist")
    reference = template_spec.get("nodeClassRef") or {}
    if reference != {
        "group": "karpenter.k8s.aws",
        "kind": "EC2NodeClass",
        "name": nodeclass,
    }:
        errors.append(f"NodePool {name} must reference EC2NodeClass {nodeclass}")
    if (
        template_spec.get("expireAfter") != "24h"
        or (spec.get("disruption") or {}).get("consolidateAfter") != "5m"
    ):
        errors.append(
            f"NodePool {name} must retain the production expiry and consolidation limits"
        )
    if gpu:
        expected_taint = [
            {"key": "nvidia.com/gpu", "value": "true", "effect": "NoSchedule"}
        ]
        if template_spec.get("taints") != expected_taint:
            errors.append(
                f"NodePool {name} must retain the nvidia.com/gpu NoSchedule taint"
            )
    return errors


@pytest.mark.validate
def validate_karpenter_capacity(context: ValidationContext) -> None:
    """Verify Karpenter EC2NodeClass and NodePool resource definitions."""
    resources = context.render("k8s/cluster/capacity/karpenter")
    cpu_class = find_resource(resources, "EC2NodeClass", "training-cpu")
    gpu_class = find_resource(resources, "EC2NodeClass", "training-gpu")
    cpu_pool = find_resource(resources, "NodePool", "mlops-paas-training-cpu")
    gpu_pool = find_resource(resources, "NodePool", "mlops-paas-training-gpu")

    errors: list[str] = []
    for resource, kind, name in (
        (cpu_class, "EC2NodeClass", "training-cpu"),
        (gpu_class, "EC2NodeClass", "training-gpu"),
        (cpu_pool, "NodePool", "mlops-paas-training-cpu"),
        (gpu_pool, "NodePool", "mlops-paas-training-gpu"),
    ):
        if not resource:
            errors.append(f"Karpenter capacity must render {kind}/{name}")

    if not errors:
        errors.extend(check_nodeclass(cpu_class, "training-cpu"))
        errors.extend(check_nodeclass(gpu_class, "training-gpu"))
        errors.extend(
            check_pool(
                cpu_pool,
                "mlops-paas-training-cpu",
                "training-cpu",
                {"c6i.2xlarge", "c6i.4xlarge"},
                gpu=False,
            )
        )
        errors.extend(
            check_pool(
                gpu_pool,
                "mlops-paas-training-gpu",
                "training-gpu",
                {"g4dn.xlarge", "g5.xlarge"},
                gpu=True,
            )
        )
    assert not errors, "\n".join(errors)


@pytest.mark.validate
def validate_cluster_secret_store(context: ValidationContext) -> None:
    """Verify ClusterSecretStore configuration and ExternalSecret bindings."""
    errors: list[str] = []
    all_resources: list[dict[str, Any]] = []
    targets: dict[tuple[str, str], str] = {}

    for source_path, expected_targets in EXTERNAL_SECRET_OWNERS.items():
        resources = context.render(source_path)
        all_resources.extend(resources)
        actual_targets = {
            (
                resource_namespace(resource),
                ((resource.get("spec") or {}).get("target") or {}).get("name"),
            )
            for resource in resources
            if resource.get("kind") == "ExternalSecret"
        }
        if actual_targets != expected_targets:
            errors.append(
                f"{source_path} ExternalSecret targets must be {sorted(expected_targets)}, found {sorted(actual_targets)}"
            )
        for resource in resources:
            if resource.get("kind") != "ExternalSecret":
                continue
            metadata = resource.get("metadata") or {}
            spec = resource.get("spec") or {}
            if (metadata.get("annotations") or {}).get(
                "argocd.argoproj.io/sync-wave"
            ) != "-1":
                errors.append(
                    f"ExternalSecret {metadata.get('name')} must use sync wave -1"
                )
            if spec.get("secretStoreRef") != {
                "kind": "ClusterSecretStore",
                "name": "aws-secrets-manager",
            }:
                errors.append(
                    f"ExternalSecret {metadata.get('name')} must use aws-secrets-manager"
                )

        for target in actual_targets:
            if not target[1]:
                errors.append(
                    f"{source_path} contains an ExternalSecret without spec.target.name"
                )
            elif target in targets:
                errors.append(
                    f"ExternalSecret target {target} is owned by both {targets[target]} and {source_path}"
                )
            else:
                targets[target] = source_path

    rendered_text = json.dumps(
        [
            resource
            for resource in all_resources
            if resource.get("kind") != "ExternalSecret"
        ],
        sort_keys=True,
    )
    for namespace, target in sorted(targets):
        if target not in rendered_text:
            errors.append(
                f"ExternalSecret target {namespace}/{target} has no consumer in its owner source"
            )

    for target in LEGACY_SHARED_SECRET_TARGETS:
        if target in rendered_text or any(
            target == target_name for _, target_name in targets
        ):
            errors.append(f"legacy shared Secret target {target} must not be rendered")

    if any(
        resource.get("kind") == "ExternalSecret"
        for resource in context.render("k8s/cluster/secret-store")
    ):
        errors.append(
            "cluster secret-store must own only ClusterSecretStore, not ExternalSecrets"
        )

    assert not errors, "\n".join(errors)


@pytest.mark.validate
def validate_storage_class(context: ValidationContext) -> None:
    """Verify default and NVMe StorageClass definitions."""
    resources = context.render("k8s/cluster/storage")
    sc = find_resource(resources, "StorageClass", "ebs-gp3")
    assert sc, "k8s/cluster/storage must render StorageClass ebs-gp3"
    assert sc.get("provisioner") == "ebs.csi.aws.com", "ebs-gp3 provisioner must be ebs.csi.aws.com"
    assert sc.get("volumeBindingMode") == "WaitForFirstConsumer"
    assert sc.get("reclaimPolicy") == "Delete"


@pytest.mark.validate
def validate_cluster_labels(context: ValidationContext) -> None:
    """Verify standard labels across cluster manifests."""
    paths = [
        "k8s/cluster/capacity/karpenter",
        "k8s/cluster/secret-store",
        "k8s/cluster/storage",
        "k8s/cluster/image",
    ]
    errors: list[str] = []
    for path in paths:
        for resource in context.render(path):
            labels = (resource.get("metadata") or {}).get("labels") or {}
            missing_app = STANDARD_APP_LABELS - set(labels.keys())
            if missing_app:
                name = (resource.get("metadata") or {}).get("name")
                errors.append(f"{path} resource {name} missing app labels: {missing_app}")
            if labels.get("mlops-paas.io/plane") != "cluster":
                name = (resource.get("metadata") or {}).get("name")
                errors.append(f"{path} resource {name} mlops-paas.io/plane must be 'cluster'")
    assert not errors, "\n".join(errors)

