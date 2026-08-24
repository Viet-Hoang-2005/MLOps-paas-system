"""Validate ExternalSecret placement, target ownership, and consumers."""

from __future__ import annotations

import json

from .common import (
    EXTERNAL_SECRET_OWNERS,
    LEGACY_SHARED_SECRET_TARGETS,
    ValidationContext,
    resource_namespace,
    run_standalone,
)


def validate(context: ValidationContext) -> list[str]:
    errors: list[str] = []
    all_resources: list[dict] = []
    targets: dict[tuple[str, str], str] = {}
    for source_path, expected_targets in EXTERNAL_SECRET_OWNERS.items():
        resources = context.render(source_path)
        all_resources.extend(resources)
        actual_targets = {
            (resource_namespace(resource), ((resource.get("spec") or {}).get("target") or {}).get("name"))
            for resource in resources
            if resource.get("kind") == "ExternalSecret"
        }
        if actual_targets != expected_targets:
            errors.append(f"{source_path} ExternalSecret targets must be {sorted(expected_targets)}, found {sorted(actual_targets)}")
        for resource in resources:
            if resource.get("kind") != "ExternalSecret":
                continue
            metadata = resource.get("metadata") or {}
            spec = resource.get("spec") or {}
            if (metadata.get("annotations") or {}).get("argocd.argoproj.io/sync-wave") != "-1":
                errors.append(f"ExternalSecret {metadata.get('name')} must use sync wave -1")
            if spec.get("secretStoreRef") != {"kind": "ClusterSecretStore", "name": "aws-secrets-manager"}:
                errors.append(f"ExternalSecret {metadata.get('name')} must use aws-secrets-manager")
        for target in actual_targets:
            if not target[1]:
                errors.append(f"{source_path} contains an ExternalSecret without spec.target.name")
            elif target in targets:
                errors.append(f"ExternalSecret target {target} is owned by both {targets[target]} and {source_path}")
            else:
                targets[target] = source_path
    rendered_text = json.dumps([resource for resource in all_resources if resource.get("kind") != "ExternalSecret"], sort_keys=True)
    for namespace, target in sorted(targets):
        if target not in rendered_text:
            errors.append(f"ExternalSecret target {namespace}/{target} has no consumer in its owner source")
    for target in LEGACY_SHARED_SECRET_TARGETS:
        if target in rendered_text or any(target == target_name for _, target_name in targets):
            errors.append(f"legacy shared Secret target {target} must not be rendered")
    if any(resource.get("kind") == "ExternalSecret" for resource in context.render("k8s/cluster/secret-store")):
        errors.append("mlops-prod-cluster-secret-store must own only ClusterSecretStore, not ExternalSecrets")
    return errors


if __name__ == "__main__":  # pragma: no cover - CLI boundary
    raise SystemExit(run_standalone("secrets", validate))
