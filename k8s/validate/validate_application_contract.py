"""Validate GitOps application topology, ownership boundaries, and sync contract."""

from __future__ import annotations

from pathlib import Path

from .common import (
    PRODUCTION_NAMESPACES,
    REPOSITORY_URL,
    WORKLOAD_APPLICATIONS,
    ValidationContext,
    application_name,
    application_sources,
    run_standalone,
    yaml_documents,
)


EXPECTED_SYNC_OPTIONS = {
    "ApplyOutOfSyncOnly=true",
    "ServerSideApply=true",
    "RespectIgnoreDifferences=true",
    "PruneLast=true",
    "FailOnSharedResource=true",
}


def validate_workload_layout(context: ValidationContext) -> list[str]:
    errors: list[str] = []
    for app_name, (service, logical_image) in WORKLOAD_APPLICATIONS.items():
        application = context.application(app_name)
        source = ((application.get("spec") or {}).get("source") or {}).get("path")
        expected = f"k8s/apps/overlays/production/{service}"
        if source != expected:
            errors.append(f"{app_name} source must be {expected}, found {source or 'missing'}")
        images: list[str] = []
        for resource in context.render(f"k8s/apps/base/{service}"):
            pod_spec = (((resource.get("spec") or {}).get("template") or {}).get("spec") or {})
            for field in ("initContainers", "containers"):
                images.extend(
                    container.get("image", "")
                    for container in pod_spec.get(field) or []
                    if container.get("image", "").split(":", 1)[0] == logical_image
                )
        if not images:
            errors.append(f"{service} base does not reference logical image {logical_image}")
        errors.extend(
            f"{service} base image must not contain a tag or digest: {image}"
            for image in images
            if image != logical_image
        )
    return errors


def validate_lifecycle(context: ValidationContext) -> list[str]:
    errors: list[str] = []
    applications = context.applications
    if len(applications) != 31:
        errors.append(f"root GitOps must render exactly 31 child Applications, found {len(applications)}")
    boundaries = {
        "k8s/cluster/": ("mlops-prod-cluster-", "mlops-cluster", "cluster"),
        "k8s/addons/": ("mlops-prod-addon-", "mlops-addons", "addon"),
        "k8s/platform/": ("mlops-prod-platform-", "mlops-platform", "platform"),
        "k8s/argo": ("mlops-prod-execution-", "mlops-execution", "execution"),
        "k8s/apps/": ("mlops-prod-workload-", "mlops-workloads", "workload"),
    }
    expected_waves = {
        "mlops-prod-cluster-namespaces": "-50",
        "mlops-prod-cluster-storage": "-30",
        "mlops-prod-cluster-secret-store": "-30",
        "mlops-prod-cluster-image-verification": "-29",
        "mlops-prod-addon-karpenter-crds": "-25",
        "mlops-prod-addon-karpenter": "-24",
        "mlops-prod-addon-kubeflow-training": "-24",
        "mlops-prod-addon-node-feature-discovery": "-24",
        "mlops-prod-cluster-karpenter-capacity": "-23",
        "mlops-prod-addon-gpu-operator": "-23",
    }
    for name in (
        "mlops-prod-addon-aws-ebs-csi",
        "mlops-prod-addon-external-secrets",
        "mlops-prod-addon-cloudnative-pg",
        "mlops-prod-addon-keda",
        "mlops-prod-addon-argo-workflows",
        "mlops-prod-addon-argo-events",
        "mlops-prod-addon-monitoring",
        "mlops-prod-addon-kyverno",
    ):
        expected_waves[name] = "-40"

    for application in applications:
        metadata = application.get("metadata") or {}
        spec = application.get("spec") or {}
        name = application_name(application)
        labels = metadata.get("labels") or {}
        sources = application_sources(application)
        project = spec.get("project")
        plane = labels.get("mlops-paas.io/plane")
        if labels.get("app.kubernetes.io/part-of") != "mlops-paas":
            errors.append(f"{name} must have app.kubernetes.io/part-of=mlops-paas")
        if labels.get("mlops-paas.io/environment") != "production":
            errors.append(f"{name} must have mlops-paas.io/environment=production")
        if not labels.get("mlops-paas.io/component"):
            errors.append(f"{name} must declare mlops-paas.io/component")
        if spec.get("revisionHistoryLimit") != 10:
            errors.append(f"{name} must use revisionHistoryLimit=10")
        policy = spec.get("syncPolicy") or {}
        automated = policy.get("automated") or {}
        if automated != {"prune": True, "selfHeal": True, "allowEmpty": False}:
            errors.append(f"{name} must use the production automated sync contract")
        if set(policy.get("syncOptions") or []) != EXPECTED_SYNC_OPTIONS:
            errors.append(f"{name} must use the shared production sync options")
        if not {entry.get("name") for entry in spec.get("info") or []} >= {"Owner", "Source", "Runbook"}:
            errors.append(f"{name} must provide Owner, Source, and Runbook info")
        if any(source.get("chart") for source in sources):
            expected = ("mlops-prod-addon-", "mlops-addons", "addon")
            if not (name.startswith(expected[0]) and project == expected[1] and plane == expected[2]):
                errors.append(f"Helm Application {name} must belong to the addons lifecycle boundary")
        else:
            paths = [source.get("path", "") for source in sources]
            boundary = next(
                (contract for prefix, contract in boundaries.items() if paths and all(path.startswith(prefix) for path in paths)),
                None,
            )
            if not boundary:
                errors.append(f"Git Application {name} has unsupported lifecycle source paths: {paths}")
            elif not (name.startswith(boundary[0]) and project == boundary[1] and plane == boundary[2]):
                errors.append(f"Git Application {name} violates its lifecycle boundary")
        expected_wave = expected_waves.get(name)
        if expected_wave and (metadata.get("annotations") or {}).get("argocd.argoproj.io/sync-wave") != expected_wave:
            errors.append(f"{name} must reconcile at sync wave {expected_wave}")
    return errors


def validate_projects_and_cluster_configuration(context: ValidationContext) -> list[str]:
    errors: list[str] = []
    root_resources = context.root_resources
    projects = {
        (resource.get("metadata") or {}).get("name"): resource
        for resource in root_resources
        if resource.get("kind") == "AppProject"
    }
    required_projects = {"mlops-cluster", "mlops-addons", "mlops-platform", "mlops-execution", "mlops-workloads"}
    if set(projects) != required_projects:
        return [f"GitOps must define exactly {sorted(required_projects)} AppProjects, found {sorted(projects)}"]
    if any(resource.get("kind") == "Namespace" for resource in root_resources):
        errors.append("root GitOps must own only control-tree resources, never Namespace resources")
    for project in ("mlops-cluster", "mlops-platform", "mlops-execution", "mlops-workloads"):
        if (projects[project].get("spec") or {}).get("sourceRepos") != [REPOSITORY_URL]:
            errors.append(f"{project} must trust only the repository Git source")
    if (projects["mlops-platform"].get("spec") or {}).get("clusterResourceBlacklist") != [{"group": "*", "kind": "*"}]:
        errors.append("mlops-platform must deny all cluster-scoped resources")
    cluster_kinds = {
        (entry.get("group"), entry.get("kind"))
        for entry in (projects["mlops-cluster"].get("spec") or {}).get("clusterResourceWhitelist") or []
    }
    expected_kinds = {
        ("", "Namespace"), ("storage.k8s.io", "StorageClass"),
        ("external-secrets.io", "ClusterSecretStore"), ("karpenter.k8s.aws", "EC2NodeClass"),
        ("karpenter.sh", "NodePool"), ("kyverno.io", "ClusterPolicy"),
    }
    if cluster_kinds != expected_kinds:
        errors.append("mlops-cluster must allow only declared cluster-configuration resource kinds")
    if (projects["mlops-addons"].get("spec") or {}).get("clusterResourceWhitelist") != [{"group": "*", "kind": "*"}]:
        errors.append("mlops-addons must retain trusted add-on chart cluster-resource allowance")

    namespaces = {
        (resource.get("metadata") or {}).get("name")
        for resource in context.render("k8s/cluster/namespaces")
        if resource.get("kind") == "Namespace"
    }
    if namespaces != PRODUCTION_NAMESPACES:
        errors.append(f"cluster namespace set must be {sorted(PRODUCTION_NAMESPACES)}, found {sorted(namespaces)}")
    namespace_app = context.application("mlops-prod-cluster-namespaces")
    if (((namespace_app.get("spec") or {}).get("source") or {}).get("path")) != "k8s/cluster/namespaces":
        errors.append("mlops-prod-cluster-namespaces must source k8s/cluster/namespaces")
    storage = context.render("k8s/cluster/storage")
    if any(resource.get("kind") == "Namespace" for resource in storage):
        errors.append("mlops-prod-cluster-storage must not own Namespace resources")
    storage_classes = {(resource.get("metadata") or {}).get("name") for resource in storage if resource.get("kind") == "StorageClass"}
    if storage_classes != {"ebs-gp3"}:
        errors.append("mlops-prod-cluster-storage must own exactly the ebs-gp3 StorageClass")
    return errors


def _walk_values(value: object):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)


def validate_no_default_namespace(context: ValidationContext) -> list[str]:
    errors: list[str] = []
    for application in context.applications:
        name = application_name(application)
        destination = ((application.get("spec") or {}).get("destination") or {})
        if destination.get("namespace") == "default":
            errors.append(f"{name} must not target the Kubernetes default namespace")

    k8s_root = context.source_root / "k8s"
    for manifest_path in sorted([*k8s_root.rglob("*.yaml"), *k8s_root.rglob("*.yml")]):
        if "charts" in manifest_path.parts:
            continue
        relative_path = manifest_path.relative_to(context.source_root).as_posix()
        content = manifest_path.read_text(encoding="utf-8")
        if ".default.svc.cluster.local" in content:
            errors.append(f"{relative_path} must not reference a Service in default.svc.cluster.local")
        for document in yaml_documents(content):
            for key, value in _walk_values(document):
                if key == "namespace" and value == "default":
                    errors.append(f"{relative_path} must not declare namespace: default")
                    break
    return errors


def validate(context: ValidationContext) -> list[str]:
    return [
        *validate_workload_layout(context),
        *validate_lifecycle(context),
        *validate_projects_and_cluster_configuration(context),
        *validate_no_default_namespace(context),
    ]


if __name__ == "__main__":  # pragma: no cover - CLI boundary
    raise SystemExit(run_standalone("application-contract", validate))
