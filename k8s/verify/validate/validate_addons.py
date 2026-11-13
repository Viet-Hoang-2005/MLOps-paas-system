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
def validate_kubeflow_trainer_addon(repo_root: Path) -> None:
    application = load_yaml_documents(repo_root / "k8s/gitops/production/applications/addons/kubeflow-trainer.yaml")[0]
    source = application["spec"]["source"]
    assert source["repoURL"] == "ghcr.io/kubeflow/charts"
    assert source["chart"] == "kubeflow-trainer" and source["targetRevision"] == "2.3.0"
    values = yaml.safe_load(source["helm"]["values"])
    assert values["crds"]["enabled"] and values["jobset"]["install"]
    assert values["jobset"]["image"]["tag"] == "v0.12.0"
    assert not values["runtimes"]["defaultEnabled"] and not values["dataCache"]["enabled"]
    assert application["spec"]["destination"]["namespace"] == "kubeflow-system"
    assert not (repo_root / "k8s/addons/kubeflow-training/kustomization.yaml").exists()


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
