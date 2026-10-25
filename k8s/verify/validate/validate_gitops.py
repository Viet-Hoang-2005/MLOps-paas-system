"""Validate GitOps App-of-apps topology, sync contracts, waves, and resource ownership."""

from __future__ import annotations

from typing import Any

import pytest

from ..utils import (
    PRODUCTION_NAMESPACES,
    REPOSITORY_URL,
    ValidationContext,
    application_name,
    application_sources,
    identity,
)

EXPECTED_SYNC_OPTIONS = {
    "ApplyOutOfSyncOnly=true",
    "ServerSideApply=true",
    "RespectIgnoreDifferences=true",
    "PruneLast=true",
    "FailOnSharedResource=true",
}


@pytest.mark.validate
def validate_gitops_application_lifecycle_and_contracts(context: ValidationContext) -> None:
    """Verify that root GitOps renders exactly 35 child Applications with required contracts."""
    applications = context.applications
    assert len(applications) == 35, (
        f"root GitOps must render exactly 35 child Applications, found {len(applications)}"
    )

    errors: list[str] = []
    for application in applications:
        name = application_name(application)
        metadata = application.get("metadata") or {}
        spec = application.get("spec") or {}
        labels = metadata.get("labels") or {}
        sources = application_sources(application)
        project = spec.get("project")
        plane = labels.get("mlops-paas.io/plane")

        if labels.get("app.kubernetes.io/part-of") != "mlops-paas":
            errors.append(f"{name} must have app.kubernetes.io/part-of=mlops-paas")
        if labels.get("mlops-paas.io/environment") != "production":
            errors.append(f"{name} must have mlops-paas.io/environment=production")
        if not labels.get("app.kubernetes.io/component"):
            errors.append(f"{name} must declare app.kubernetes.io/component")
        if spec.get("revisionHistoryLimit") != 10:
            errors.append(f"{name} must use revisionHistoryLimit=10")

        policy = spec.get("syncPolicy") or {}
        automated = policy.get("automated") or {}
        if automated != {"prune": True, "selfHeal": True, "allowEmpty": False}:
            errors.append(f"{name} must use the production automated sync contract")
        if set(policy.get("syncOptions") or []) != EXPECTED_SYNC_OPTIONS:
            errors.append(f"{name} must use the shared production sync options")

        if any(source.get("chart") for source in sources):
            expected = ("mlops-prod-addon-", "mlops-addons", "addon")
            if not (
                name.startswith(expected[0])
                and project == expected[1]
                and plane == expected[2]
            ):
                errors.append(f"Helm Application {name} must belong to addons boundary")

    assert not errors, "\n".join(errors)


@pytest.mark.validate
def validate_resource_ownership(context: ValidationContext) -> None:
    """Verify that no two Argo Applications claim ownership over the same Kubernetes resource."""
    errors: list[str] = []
    owners: dict[tuple[str, str, str, str], str] = {}
    helm_releases: dict[tuple[str, str], str] = {}

    from concurrent.futures import ThreadPoolExecutor

    paths_to_render = {
        source["path"]
        for app in context.applications
        for source in application_sources(app)
        if source.get("repoURL") == REPOSITORY_URL and source.get("path")
    }
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(context.render, paths_to_render))

    for application in context.applications:
        name = application_name(application)
        destination_ns = ((application.get("spec") or {}).get("destination") or {}).get("namespace", "default")
        for source in application_sources(application):
            # Skip values-only reference sources (Multiple Sources)
            if source.get("ref"):
                continue
            if source.get("repoURL") == REPOSITORY_URL and source.get("path"):
                resources = context.render(source["path"])
                for resource in resources:
                    resource_id = identity(resource)
                    if resource_id in owners:
                        errors.append(
                            f"Resource {resource_id} is owned by both {owners[resource_id]} and {name}"
                        )
                    else:
                        owners[resource_id] = name
            elif source.get("chart"):
                chart_key = (source["chart"], destination_ns)
                if chart_key in helm_releases:
                    errors.append(
                        f"Helm chart {chart_key} is declared by both {helm_releases[chart_key]} and {name}"
                    )
                else:
                    helm_releases[chart_key] = name
            else:
                errors.append(f"{name} has an unsupported Application source: {source}")
                continue

    assert not errors, "\n".join(errors)
