"""Stateless normalization and artifact metadata helpers."""

import hashlib
from urllib.parse import urlparse


def safe_json_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [safe_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): safe_json_value(item) for key, item in value.items()}
    return str(value)


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def artifact_kind(relative_path, model_extensions, checkpoint_extensions,
                  metadata_extensions) -> str:
    name = relative_path.name
    suffix = relative_path.suffix.lower()
    if name == "MLmodel" or suffix in model_extensions:
        return "model"
    if suffix in checkpoint_extensions:
        return "checkpoint"
    if suffix in metadata_extensions:
        return "metadata"
    if suffix == ".log":
        return "log"
    return "other"


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mlflow_proxy_artifact_uri(artifact_root: str) -> str:
    parsed = urlparse(artifact_root)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        raise RuntimeError(f"Invalid S3 URI for MLflow artifacts: {artifact_root!r}")
    return f"mlflow-artifacts:/{parsed.path.lstrip('/')}"
