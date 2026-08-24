"""Validate production Karpenter CPU/GPU capacity contracts."""

from __future__ import annotations

from .common import ValidationContext, find_resource, run_standalone


def requirement_values(pool: dict, key: str) -> set[str]:
    for requirement in (((pool.get("spec") or {}).get("template") or {}).get("spec") or {}).get("requirements") or []:
        if requirement.get("key") == key:
            return set(requirement.get("values") or [])
    return set()


def validate_nodeclass(nodeclass: dict, name: str) -> list[str]:
    errors: list[str] = []
    spec = nodeclass.get("spec") or {}
    options = spec.get("metadataOptions") or {}
    expected_options = {"httpEndpoint": "enabled", "httpProtocolIPv6": "disabled", "httpPutResponseHopLimit": 1, "httpTokens": "required"}
    if options != expected_options:
        errors.append(f"EC2NodeClass {name} must require IMDSv2 with hop limit 1")
    if spec.get("amiFamily") != "Custom" or spec.get("instanceProfile") != "mlops-karpenter-node-profile":
        errors.append(f"EC2NodeClass {name} must use the production custom AMI and instance profile")
    user_data = spec.get("userData") or ""
    if "--secret-id mlops/k3s-agent-token" not in user_data or "k3s-api.internal.mlops-nids-nt114.id.vn:6443" not in user_data:
        errors.append(f"EC2NodeClass {name} must retrieve the join token from Secrets Manager and join private K3s DNS")
    if "K3S_TOKEN=\"K10" in user_data or "K3S_TOKEN='K10" in user_data:
        errors.append(f"EC2NodeClass {name} must not embed a K3s token in Git")
    return errors


def validate_pool(pool: dict, name: str, nodeclass: str, instances: set[str], *, gpu: bool) -> list[str]:
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
    if reference != {"group": "karpenter.k8s.aws", "kind": "EC2NodeClass", "name": nodeclass}:
        errors.append(f"NodePool {name} must reference EC2NodeClass {nodeclass}")
    if template_spec.get("expireAfter") != "24h" or (spec.get("disruption") or {}).get("consolidateAfter") != "5m":
        errors.append(f"NodePool {name} must retain the production expiry and consolidation limits")
    if gpu:
        expected_taint = [{"key": "nvidia.com/gpu", "value": "true", "effect": "NoSchedule"}]
        if template_spec.get("taints") != expected_taint:
            errors.append(f"NodePool {name} must retain the nvidia.com/gpu NoSchedule taint")
    return errors


def validate(context: ValidationContext) -> list[str]:
    resources = context.render("k8s/cluster/capacity/karpenter")
    errors: list[str] = []
    cpu_class = find_resource(resources, "EC2NodeClass", "training-cpu")
    gpu_class = find_resource(resources, "EC2NodeClass", "training-gpu")
    cpu_pool = find_resource(resources, "NodePool", "mlops-paas-training-cpu")
    gpu_pool = find_resource(resources, "NodePool", "mlops-paas-training-gpu")
    for resource, kind, name in ((cpu_class, "EC2NodeClass", "training-cpu"), (gpu_class, "EC2NodeClass", "training-gpu"), (cpu_pool, "NodePool", "mlops-paas-training-cpu"), (gpu_pool, "NodePool", "mlops-paas-training-gpu")):
        if not resource:
            errors.append(f"Karpenter capacity must render {kind}/{name}")
    if errors:
        return errors
    return [
        *validate_nodeclass(cpu_class, "training-cpu"),
        *validate_nodeclass(gpu_class, "training-gpu"),
        *validate_pool(cpu_pool, "mlops-paas-training-cpu", "training-cpu", {"c6i.2xlarge", "c6i.4xlarge"}, gpu=False),
        *validate_pool(gpu_pool, "mlops-paas-training-gpu", "training-gpu", {"g4dn.xlarge", "g5.xlarge"}, gpu=True),
    ]


if __name__ == "__main__":  # pragma: no cover - CLI boundary
    raise SystemExit(run_standalone("cluster-capacity", validate))
