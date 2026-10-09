"""Stateless normalization and artifact metadata helpers."""

import hashlib
import math
from urllib.parse import urlparse


def count_non_finite(value) -> int:
    """How many NaN/Infinity numbers a JSON-like value holds."""
    if isinstance(value, float):
        return 0 if math.isfinite(value) else 1
    if isinstance(value, (list, tuple)):
        return sum(count_non_finite(item) for item in value)
    if isinstance(value, dict):
        return sum(count_non_finite(item) for item in value.values())
    return 0


def safe_json_value(value):
    # NaN and Infinity are not JSON: strict parsers (the Control Plane's included) reject them.
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [safe_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): safe_json_value(item) for key, item in value.items()}
    return str(value)


def is_number(value) -> bool:
    """A finite number: NaN and Infinity cannot be reported as a metric."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def artifact_kind(relative_path, model_extensions, checkpoint_extensions, metadata_extensions) -> str:
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
