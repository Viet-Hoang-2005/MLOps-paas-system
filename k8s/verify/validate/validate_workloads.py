"""Validate Workload Plane resources: 7 microservices, Celery isolation, and base images."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ..utils import (
    STANDARD_APP_LABELS,
    STANDARD_MLOPS_LABELS,
    WORKLOAD_APPLICATIONS,
    ValidationContext,
)


@pytest.mark.validate
def validate_workload_layout_and_images(context: ValidationContext) -> None:
    """Verify workload applications point to correct overlays and bases don't hardcode digests."""
    errors: list[str] = []
    for app_name, (service, logical_image) in WORKLOAD_APPLICATIONS.items():
        application = context.application(app_name)
        source = ((application.get("spec") or {}).get("source") or {}).get("path")
        expected = f"k8s/apps/overlays/production/{service}"
        if source != expected:
            errors.append(
                f"{app_name} source must be {expected}, found {source or 'missing'}"
            )
        images: list[str] = []
        for resource in context.render(f"k8s/apps/base/{service}"):
            pod_spec = ((resource.get("spec") or {}).get("template") or {}).get(
                "spec"
            ) or {}
            for field in ("initContainers", "containers"):
                images.extend(
                    container.get("image", "")
                    for container in pod_spec.get(field) or []
                    if container.get("image", "").split(":", 1)[0] == logical_image
                )
        if not images:
            errors.append(
                f"{service} base does not reference logical image {logical_image}"
            )
        errors.extend(
            f"{service} base image must not contain a tag or digest: {image}"
            for image in images
            if image != logical_image
        )
    assert not errors, "\n".join(errors)


@pytest.mark.validate
def validate_celery_process_isolation(repo_root: Path) -> None:
    """Verify that Celery worker, beat, and health-worker remain strictly isolated Deployments."""
    path = repo_root / "k8s/apps/base/control-plane/celery-deployment.yaml"
    resources = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))

    # Assert exactly 3 deployments
    deployments = [r for r in resources if r.get("kind") == "Deployment"]
    names = {r["metadata"]["name"] for r in deployments}
    assert names == {
        "mlops-paas-celery-worker",
        "mlops-paas-celery-beat",
        "mlops-paas-celery-health-worker",
    }, f"Unexpected Celery deployment names: {names}"

    # Assert Beat uses Recreate strategy
    beat = next(r for r in deployments if r["metadata"]["name"] == "mlops-paas-celery-beat")
    assert (beat.get("spec") or {}).get("strategy", {}).get("type") == "Recreate", (
        "Celery Beat must use Recreate strategy to prevent duplicate schedulers"
    )


@pytest.mark.validate
def validate_workload_standard_labels(context: ValidationContext) -> None:
    """Verify standard labels across workload bases and overlays."""
    paths = [
        "k8s/apps/base/control-plane",
        "k8s/apps/base/consumer",
        "k8s/apps/base/model-server",
        "k8s/apps/base/web",
    ]
    errors: list[str] = []
    for path in paths:
        for resource in context.render(path):
            labels = (resource.get("metadata") or {}).get("labels") or {}
            missing_app = STANDARD_APP_LABELS - set(labels.keys())
            if missing_app:
                name = (resource.get("metadata") or {}).get("name")
                errors.append(f"{path} resource {name} missing app labels: {missing_app}")
            missing_mlops = STANDARD_MLOPS_LABELS - set(labels.keys())
            if missing_mlops:
                name = (resource.get("metadata") or {}).get("name")
                errors.append(f"{path} resource {name} missing mlops labels: {missing_mlops}")
    assert not errors, "\n".join(errors)

