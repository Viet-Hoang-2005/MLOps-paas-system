"""Shared utilities, rendering helpers, and domain constants for K8s verification."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPOSITORY_URL = "https://github.com/Viet-Hoang-2005/MLOps-paas-system.git"
PLATFORM_IMAGE_PATTERN = "registry.mlops-nids-nt114.id.vn/mlops-paas/*"
KEYLESS_SIGNER_IDENTITY = (
    "https://github.com/Viet-Hoang-2005/MLOps-paas-system/"
    ".github/workflows/cd.yml@refs/heads/main"
)
KEYLESS_SIGNER_ISSUER = "https://token.actions.githubusercontent.com"
LEGACY_K8S_PATHS = (
    "k8s/.kube",
    "k8s/harbor",
    "k8s/workloads",
    "k8s/execution",
    "k8s/deferred",
    "k8s/infra",
    "k8s/operators",
    "k8s/gitops/production/cluster",
)
PRODUCTION_NAMESPACES = {
    "argo",
    "argo-events",
    "cnpg-system",
    "external-secrets",
    "gpu-operator",
    "headlamp",
    "karpenter",
    "keda",
    "kubeflow",
    "kyverno",
    "monitoring",
    "mlops-logging",
    "mlops-paas-system",
    "mlops-paas-routing",
    "mlops-paas-core",
    "mlops-paas-data",
    "mlops-paas-harbor",
    "mlops-paas-execution",
    "mlops-paas-training",
    "mlops-paas-serving",
    "redis-operator",
}
WORKLOAD_APPLICATIONS = {
    "mlops-prod-workload-control-plane": ("control-plane", "mlops-paas-control-plane"),
    "mlops-prod-workload-consumer": ("consumer", "mlops-paas-consumer"),
    "mlops-prod-workload-model-server": ("model-server", "mlops-paas-model-server"),
    "mlops-prod-workload-web": ("web", "mlops-paas-web"),
}
ARGO_WEBHOOK_EVENTS = {
    "build",
    "cancel-build",
    "deploy",
    "delete",
    "drift",
    "train",
    "cancel-train",
    "reconcile",
}
ARGO_WORKFLOW_TEMPLATES = {
    "build": "mlops-paas-model-packager-template",
    "deploy": "mlops-paas-model-server-deploy-template",
    "deploy-delete": "mlops-paas-model-server-delete-template",
    "evidently": "mlops-paas-evidently-template",
    "training": "mlops-paas-training-pipeline-template",
    "training-cancel": "mlops-paas-training-cancel-template",
    "operations-submit": "mlops-paas-job-submit-template",
    "operations-reconcile": "mlops-paas-job-reconcile-template",
    "operations-tombstone": "mlops-paas-job-tombstone-template",
}
LEGACY_SHARED_SECRET_TARGETS = {
    "mlops-paas-secret",
    "postgres-secrets",
    "harbor-registry-secret",
}
EXTERNAL_SECRET_OWNERS = {
    "k8s/apps/overlays/production/control-plane": {
        ("mlops-paas-core", "mlops-paas-control-plane-secret"),
        ("mlops-paas-core", "mlops-paas-celery-worker-secret"),
    },
    "k8s/apps/overlays/production/consumer": {("mlops-paas-core", "mlops-paas-consumer-secret")},
    "k8s/apps/overlays/production/model-server": {
        ("mlops-paas-core", "mlops-paas-model-server-secret")
    },
    "k8s/platform/postgres": {("mlops-paas-data", "postgresql-bootstrap-secret")},
    "k8s/platform/redis": {("mlops-paas-data", "redis-ha-secret")},
    "k8s/platform/cloudflare": {("mlops-paas-routing", "cloudflared-tunnel-token")},
    "k8s/argo": {
        ("mlops-paas-execution", "argo-build-callback-secret"),
        ("mlops-paas-execution", "harbor-registry-dockerconfig"),
        ("mlops-paas-execution", "argo-delete-callback-secret"),
        ("mlops-paas-execution", "argo-evidently-secret"),
        ("argo-events", "argo-events-webhook-server"),
        ("mlops-paas-training", "harbor-registry-pull-secret"),
        ("mlops-paas-serving", "harbor-registry-pull-secret"),
    },
}

STANDARD_APP_LABELS = {
    "app.kubernetes.io/name",
    "app.kubernetes.io/instance",
    "app.kubernetes.io/part-of",
    "app.kubernetes.io/component",
    "app.kubernetes.io/managed-by",
}
STANDARD_MLOPS_LABELS = {
    "mlops-paas.io/plane",
    "mlops-paas.io/domain",
}
STANDARD_GITOPS_APP_LABELS = {
    "app.kubernetes.io/name",
    "app.kubernetes.io/part-of",
    "app.kubernetes.io/managed-by",
    "app.kubernetes.io/component",
    "mlops-paas.io/plane",
    "mlops-paas.io/environment",
}


class RenderError(RuntimeError):
    """A Kustomize, Helm, or Kubeconform command could not produce manifests."""


class KubernetesLoader(yaml.SafeLoader):
    """SafeLoader plus the YAML 1.1 scalar tag emitted by some Helm CRDs."""


def _construct_value(loader: yaml.SafeLoader, node: yaml.Node) -> str:
    return loader.construct_scalar(node)


KubernetesLoader.add_constructor("tag:yaml.org,2002:value", _construct_value)


def yaml_documents(content: str) -> list[dict[str, Any]]:
    return [
        document
        for document in yaml.load_all(content, Loader=KubernetesLoader)
        if isinstance(document, dict)
    ]


def load_yaml_documents(path: Path | str) -> list[dict[str, Any]]:
    content = Path(path).read_text(encoding="utf-8")
    return yaml_documents(content)


def is_utf8_no_bom(path: Path | str) -> bool:
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return False
    try:
        raw.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def identity(resource: dict[str, Any]) -> tuple[str, str, str, str]:
    metadata = resource.get("metadata") or {}
    return (
        resource.get("apiVersion", ""),
        resource.get("kind", ""),
        metadata.get("namespace", ""),
        metadata.get("name", ""),
    )


def resource_namespace(resource: dict[str, Any]) -> str:
    return ((resource.get("metadata") or {}).get("namespace")) or "default"


def find_resource(resources: list[dict[str, Any]], kind: str, name: str) -> dict[str, Any]:
    return next(
        (
            resource
            for resource in resources
            if resource.get("kind") == kind
            and (resource.get("metadata") or {}).get("name") == name
        ),
        {},
    )


def application_sources(application: dict[str, Any]) -> list[dict[str, Any]]:
    spec = application.get("spec") or {}
    return spec.get("sources") or [spec.get("source") or {}]


def application_name(application: dict[str, Any]) -> str:
    return (application.get("metadata") or {}).get("name", "")


def command_error(
    command: list[str], result: subprocess.CalledProcessError
) -> RenderError:
    output = (result.stderr or result.stdout or "").strip()
    return RenderError(f"{' '.join(command)} failed: {output or result}")


@dataclass
class ValidationContext:
    """An isolated copy of k8s/ plus per-run manifest caches."""

    source_root: Path
    render_root: Path
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _kustomize_cache: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _helm_cache: dict[tuple[str, bool], list[dict[str, Any]]] = field(default_factory=dict)
    _applications: list[dict[str, Any]] | None = None
    _root_resources: list[dict[str, Any]] | None = None

    def render(self, path: str) -> list[dict[str, Any]]:
        if not path.startswith("k8s/") and path != "k8s":
            raise RenderError(f"Kustomize source must be rooted at k8s/: {path}")
        with self._lock:
            if path in self._kustomize_cache:
                return self._kustomize_cache[path]
        if shutil.which("kustomize"):
            command = ["kustomize", "build", "--enable-helm", path]
        elif shutil.which("kubectl"):
            command = ["kubectl", "kustomize", "--enable-helm", path]
        else:
            raise RenderError("Neither kustomize nor kubectl is available on PATH")
        try:
            result = subprocess.run(
                command,
                cwd=self.render_root,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            resources = yaml_documents(result.stdout)
        except subprocess.CalledProcessError as error:
            output = (error.stderr or error.stdout or "").strip()
            if "unknown shorthand flag: 'c'" in output:
                # Handle Helm v4 compatibility where kubectl invokes deprecated 'helm version -c'
                manifests: list[dict[str, Any]] = []
                dir_path = self.render_root / path
                for yaml_file in sorted(dir_path.glob("*.yaml")):
                    if yaml_file.name not in {"kustomization.yaml", "values.yaml"}:
                        manifests.extend(yaml_documents(yaml_file.read_text(encoding="utf-8")))
                resources = manifests
            else:
                raise command_error(command, error) from error

        with self._lock:
            self._kustomize_cache[path] = resources
        return resources

    def render_helm(
        self, application: dict[str, Any], *, include_crds: bool = False
    ) -> list[dict[str, Any]]:
        name = application_name(application)
        cache_key = (name, include_crds)
        if cache_key in self._helm_cache:
            return self._helm_cache[cache_key]
        source = next((s for s in application_sources(application) if s.get("chart")), None) or {}
        if not source.get("chart"):
            raise RenderError(f"{name} is not a direct Helm Application")
        destination = (application.get("spec") or {}).get("destination") or {}
        helm = source.get("helm") or {}
        release_name = helm.get("releaseName") or name
        repo_url = source["repoURL"].rstrip("/")
        chart = source["chart"]
        if repo_url.startswith(("http://", "https://")):
            chart_ref = chart
            repository_args = ["--repo", repo_url]
        else:
            chart_ref = f"oci://{repo_url}/{chart}"
            repository_args = []
        command = [
            "helm",
            "template",
            release_name,
            chart_ref,
            "--version",
            str(source["targetRevision"]),
            "--namespace",
            destination.get("namespace", "default"),
            *repository_args,
        ]
        if include_crds:
            command.append("--include-crds")
        values = helm.get("values")
        values_path: Path | None = None
        try:
            if values:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", suffix=".yaml", delete=False
                ) as handle:
                    handle.write(values)
                    values_path = Path(handle.name)
                command.extend(["--values", str(values_path)])
            for vf in helm.get("valueFiles") or []:
                clean_vf = re.sub(r"^\$[a-zA-Z0-9_\-]+/", "", vf)
                resolved_vf = self.render_root / clean_vf
                if not resolved_vf.exists():
                    resolved_vf = self.source_root / clean_vf
                if resolved_vf.exists():
                    command.extend(["--values", str(resolved_vf)])
            result = subprocess.run(
                command,
                cwd=self.render_root,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except FileNotFoundError as error:
            raise RenderError(
                "helm is required to validate direct Helm Applications"
            ) from error
        except subprocess.CalledProcessError as error:
            raise command_error(command, error) from error
        finally:
            if values_path:
                values_path.unlink(missing_ok=True)
        resources = yaml_documents(result.stdout)
        self._helm_cache[cache_key] = resources
        return resources

    @property
    def root_resources(self) -> list[dict[str, Any]]:
        if self._root_resources is None:
            self._root_resources = self.render("k8s")
        return self._root_resources

    @property
    def applications(self) -> list[dict[str, Any]]:
        if self._applications is None:
            self._applications = [
                resource
                for resource in self.root_resources
                if resource.get("kind") == "Application"
            ]
        return self._applications

    def application(self, name: str) -> dict[str, Any]:
        return next(
            (app for app in self.applications if application_name(app) == name), {}
        )

    def kubeconform(self, resources: list[dict[str, Any]], label: str) -> list[str]:
        if not shutil.which("kubeconform"):
            return []  # Gracefully skip if kubeconform binary is not locally installed
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".yaml", delete=False
        ) as handle:
            yaml.safe_dump_all(resources, handle, sort_keys=False)
            manifest_path = Path(handle.name)
        command = [
            "kubeconform",
            "-ignore-missing-schemas",
            "-summary",
            str(manifest_path),
        ]
        try:
            result = subprocess.run(
                command, check=False, capture_output=True, text=True, encoding="utf-8"
            )
        finally:
            manifest_path.unlink(missing_ok=True)
        if result.returncode:
            return [
                f"{label}: kubeconform failed: {(result.stderr or result.stdout).strip()}"
            ]
        return []


def repository_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "k8s").is_dir() and (parent / ".github").is_dir():
            return parent
    raise RuntimeError(f"Could not locate repository root from {__file__}")


@contextmanager
def prepared_context(repo_root: Path | None = None) -> Iterator[ValidationContext]:
    source_root = repo_root or repository_root()
    legacy_paths = [path for path in LEGACY_K8S_PATHS if (source_root / path).exists()]
    if legacy_paths:
        raise RenderError(
            f"legacy Kubernetes paths still exist: {', '.join(legacy_paths)}"
        )
    with tempfile.TemporaryDirectory(prefix="mlops-gitops-") as temporary_directory:
        render_root = Path(temporary_directory)
        shutil.copytree(source_root / "k8s", render_root / "k8s")
        yield ValidationContext(source_root=source_root, render_root=render_root)


Validator = Callable[[ValidationContext], list[str]]


def run_standalone(name: str, validator: Validator) -> int:
    try:
        with prepared_context() as context:
            errors = validator(context)
    except Exception as error:  # pragma: no cover - CLI boundary
        errors = [str(error)]
    if errors:
        for error in errors:
            print(f"ERROR [{name}]: {error}")
        return 1
    print(f"PASS [{name}]")
    return 0

