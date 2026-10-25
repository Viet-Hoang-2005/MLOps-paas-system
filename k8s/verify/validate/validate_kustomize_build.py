"""Validate that every Kustomize package renders without syntax or schema errors."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ..utils import ValidationContext, load_yaml_documents


@pytest.mark.validate
def validate_root_kustomize_build(context: ValidationContext) -> None:
    """Verify that root k8s/ renders successfully via Kustomize."""
    resources = context.render("k8s")
    assert resources, "Root k8s/ must render at least one Kubernetes resource."


@pytest.mark.validate
def validate_production_workload_overlays(context: ValidationContext) -> None:
    """Verify that every workload production overlay builds successfully."""
    overlays = [
        "k8s/apps/overlays/production/control-plane",
        "k8s/apps/overlays/production/consumer",
        "k8s/apps/overlays/production/model-server",
        "k8s/apps/overlays/production/web",
    ]
    for overlay_path in overlays:
        resources = context.render(overlay_path)
        assert resources, f"Overlay {overlay_path} rendered zero resources."


@pytest.mark.validate
def validate_all_kustomization_references_exist(repo_root: Path) -> None:
    """Statically verify that every kustomization.yaml points to existing files/dirs."""
    errors: list[str] = []
    k8s_dir = repo_root / "k8s"

    for kust_path in k8s_dir.rglob("kustomization.yaml"):
        dir_path = kust_path.parent
        try:
            content = kust_path.read_text(encoding="utf-8")
            doc = yaml.safe_load(content)
        except Exception as exc:
            errors.append(f"{kust_path} YAML error: {exc}")
            continue

        if not isinstance(doc, dict):
            continue

        # Check resources
        for resource in doc.get("resources") or []:
            # Ignore remote URLs like github.com/...
            if "://" in resource or resource.startswith("github.com/"):
                continue
            res_path = dir_path / resource
            if not res_path.exists():
                errors.append(f"{kust_path}: resource '{resource}' does not exist on disk")

        # Check patches
        for patch in doc.get("patches") or []:
            if isinstance(patch, dict) and patch.get("path"):
                patch_file = dir_path / patch["path"]
                if not patch_file.is_file():
                    errors.append(f"{kust_path}: patch file '{patch['path']}' does not exist")

    assert not errors, "\n".join(errors)
