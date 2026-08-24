"""Render and schema-validate every direct Helm Argo CD Application source."""

from __future__ import annotations

from .common import ValidationContext, application_name, application_sources, run_standalone


def validate(context: ValidationContext) -> list[str]:
    errors: list[str] = []
    helm_apps = [application for application in context.applications if any(source.get("chart") for source in application_sources(application))]
    if not helm_apps:
        return ["GitOps must define direct Helm Applications for upstream add-ons"]
    for application in helm_apps:
        name = application_name(application)
        source = (application.get("spec") or {}).get("source") or {}
        for field in ("repoURL", "chart", "targetRevision"):
            if not source.get(field):
                errors.append(f"{name} direct Helm source must set {field}")
        resources = context.render_helm(application, include_crds=True)
        if not resources:
            errors.append(f"{name} Helm source must render at least one resource")
            continue
        errors.extend(context.kubeconform(resources, name))
    return errors


if __name__ == "__main__":  # pragma: no cover - CLI boundary
    raise SystemExit(run_standalone("helm-sources", validate))
