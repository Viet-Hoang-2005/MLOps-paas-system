"""Validate Addon Plane resources: Helm sources, Multiple Sources, and Kubeflow manifests."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from ..utils import (
    STANDARD_APP_LABELS,
    STANDARD_GITOPS_APP_LABELS,
    ValidationContext,
    application_name,
    application_sources,
    load_yaml_documents,
)


@pytest.mark.validate
def validate_helm_addon_sources(context: ValidationContext) -> None:
    """Verify that all upstream add-on Applications define valid direct Helm or Multiple Sources (pure static)."""
    errors: list[str] = []
    helm_apps = [
        application
        for application in context.applications
        if any(source.get("chart") for source in application_sources(application))
    ]
    assert helm_apps, "GitOps must define direct Helm Applications for upstream add-ons."

    for application in helm_apps:
        name = application_name(application)
        source = next((s for s in application_sources(application) if s.get("chart")), None) or {}
        for field in ("repoURL", "chart", "targetRevision"):
            if not source.get(field):
                errors.append(f"{name} direct Helm source must set {field}")

        repo_url = str(source.get("repoURL", ""))
        if not (repo_url.startswith(("http://", "https://", "oci://")) or "." in repo_url):
            errors.append(f"{name} repoURL must start with https:// or be an OCI registry, found {repo_url}")

        rev = str(source.get("targetRevision", ""))
        if rev in {"latest", "master", "main", "HEAD", ""}:
            errors.append(f"{name} targetRevision must be pinned to a semantic version, found '{rev}'")

        # Validate Multiple Sources and valueFiles resolution
        helm_spec = source.get("helm") or {}
        for vf in helm_spec.get("valueFiles") or []:
            if not (vf.startswith("$") or vf.startswith("values")):
                errors.append(f"{name} valueFiles path {vf} must start with a repo alias e.g. $values/")
            clean_vf = re.sub(r"^\$[a-zA-Z0-9_\-]+/", "", vf)
            resolved_vf = context.source_root / clean_vf
            if not resolved_vf.is_file():
                errors.append(f"{name} valueFile {vf} (resolved: {clean_vf}) does not exist on disk")

        # Validate inlined values syntax if present
        inlined_values = helm_spec.get("values")
        if inlined_values:
            try:
                parsed = yaml.safe_load(inlined_values)
                if not isinstance(parsed, dict):
                    errors.append(f"{name} inlined values must parse to a mapping")
            except Exception as exc:
                errors.append(f"{name} inlined values YAML parse error: {exc}")

    assert not errors, "\n".join(errors)


@pytest.mark.validate
def validate_kubeflow_training_addon(repo_root: Path) -> None:
    """Verify Kubeflow training addon patch and resources (pure static, no remote git clone)."""
    patch_file = repo_root / "k8s/addons/kubeflow-training/deployment-patch.yaml"
    assert patch_file.is_file(), "deployment-patch.yaml missing in k8s/addons/kubeflow-training"
    docs = load_yaml_documents(patch_file)
    assert docs, "deployment-patch.yaml contains no valid YAML documents"
    deployment = docs[0]
    labels = (deployment.get("metadata") or {}).get("labels") or {}
    missing = STANDARD_APP_LABELS - set(labels.keys())
    assert not missing, f"Kubeflow training-operator missing app labels: {missing}"
    assert labels.get("mlops-paas.io/plane") == "addon", "Kubeflow plane must be 'addon'"

    # Verify kustomization references deployment-patch.yaml
    kust_file = repo_root / "k8s/addons/kubeflow-training/kustomization.yaml"
    kust_docs = load_yaml_documents(kust_file)
    assert kust_docs, "kustomization.yaml in kubeflow-training is empty"
    patches = kust_docs[0].get("patches") or []
    has_deploy_patch = any(
        isinstance(p, dict) and p.get("path") == "deployment-patch.yaml"
        for p in patches
    )
    assert has_deploy_patch, "Kubeflow kustomization must reference deployment-patch.yaml"


@pytest.mark.validate
def validate_addon_gitops_application_labels(context: ValidationContext) -> None:
    """Verify that all addon Argo Applications follow the standard label schema."""
    errors: list[str] = []
    addon_apps = [
        app for app in context.applications
        if ((app.get("metadata") or {}).get("labels") or {}).get("mlops-paas.io/plane") == "addon"
    ]
    assert addon_apps, "No addon applications found in GitOps."
    for app in addon_apps:
        name = application_name(app)
        labels = (app.get("metadata") or {}).get("labels") or {}
        missing = STANDARD_GITOPS_APP_LABELS - set(labels.keys())
        if missing:
            errors.append(f"Addon Application {name} missing GitOps labels: {missing}")
    assert not errors, "\n".join(errors)
