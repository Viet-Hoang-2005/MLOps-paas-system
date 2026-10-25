"""Validate UTF-8 No BOM encoding, YAML syntax, and basic K8s resource structure."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ..utils import is_utf8_no_bom


@pytest.mark.validate
def validate_utf8_no_bom(all_k8s_yaml_files: list[Path]) -> None:
    """Verify that every YAML manifest is valid UTF-8 without Byte Order Mark (BOM)."""
    assert all_k8s_yaml_files, "No YAML manifests found in k8s/ directory."
    errors: list[str] = []
    for file_path in all_k8s_yaml_files:
        if not is_utf8_no_bom(file_path):
            errors.append(f"{file_path} contains BOM or invalid UTF-8 encoding")
    assert not errors, "\n".join(errors)


@pytest.mark.validate
def validate_yaml_syntax(all_k8s_yaml_files: list[Path]) -> None:
    """Verify that every YAML manifest parses cleanly with PyYAML."""
    errors: list[str] = []
    for file_path in all_k8s_yaml_files:
        try:
            content = file_path.read_text(encoding="utf-8")
            list(yaml.safe_load_all(content))
        except Exception as exc:
            errors.append(f"{file_path}: YAML parsing failed: {exc}")
    assert not errors, "\n".join(errors)


@pytest.mark.validate
def validate_kubernetes_resource_structure(all_k8s_yaml_files: list[Path]) -> None:
    """Verify that every resource manifest has valid apiVersion, kind, and metadata."""
    errors: list[str] = []
    for file_path in all_k8s_yaml_files:
        # Skip pure patch files or non-resource files that might have fragments
        if "patch" in file_path.name.lower() or file_path.name == "values.yaml":
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
            docs = list(yaml.safe_load_all(content))
        except Exception:
            continue  # Already caught by validate_yaml_syntax

        for idx, doc in enumerate(docs):
            if not isinstance(doc, dict):
                continue
            # Check Kustomization
            if doc.get("kind") == "Kustomization":
                if not doc.get("apiVersion"):
                    errors.append(f"{file_path} doc #{idx}: Kustomization missing apiVersion")
                continue

            # If it's a Kubernetes manifest
            if "apiVersion" in doc or "kind" in doc:
                if not doc.get("apiVersion"):
                    errors.append(f"{file_path} doc #{idx}: Missing apiVersion")
                if not doc.get("kind"):
                    errors.append(f"{file_path} doc #{idx}: Missing kind")
                metadata = doc.get("metadata")
                if not isinstance(metadata, dict):
                    errors.append(f"{file_path} doc #{idx}: metadata must be a dictionary")
                elif not metadata.get("name") and not metadata.get("generateName"):
                    errors.append(f"{file_path} doc #{idx}: metadata missing name/generateName")

    assert not errors, "\n".join(errors)

