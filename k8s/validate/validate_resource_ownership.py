"""Validate resource identity and single Argo CD Application ownership."""

from __future__ import annotations

from .common import REPOSITORY_URL, ValidationContext, application_name, application_sources, identity, run_standalone


def validate(context: ValidationContext) -> list[str]:
    errors: list[str] = []
    owners: dict[tuple[str, str, str, str], str] = {}
    resource_count = 0
    for application in context.applications:
        name = application_name(application)
        for source in application_sources(application):
            if source.get("repoURL") == REPOSITORY_URL and source.get("path"):
                resources = context.render(source["path"])
            elif source.get("chart"):
                resources = context.render_helm(application)
            else:
                errors.append(f"{name} has an unsupported Application source")
                continue
            for resource in resources:
                key = identity(resource)
                if not all((key[0], key[1], key[3])):
                    errors.append(f"{name} renders a resource without a complete identity: {key}")
                    continue
                resource_count += 1
                previous = owners.get(key)
                if previous:
                    errors.append(f"{key} is owned by both {previous} and {name}")
                else:
                    owners[key] = name
    if not errors:
        print(f"Validated {len(context.applications)} Argo CD Applications and {resource_count} rendered resources.")
    return errors


if __name__ == "__main__":  # pragma: no cover - CLI boundary
    raise SystemExit(run_standalone("resource-ownership", validate))
