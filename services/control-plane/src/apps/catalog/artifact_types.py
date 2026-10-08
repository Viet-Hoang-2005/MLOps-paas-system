from pathlib import Path

from rest_framework.exceptions import ValidationError

ARTIFACT_FORMATS = (
    ("raw", "Raw model"),
    ("mlflow_zip", "MLflow model package ZIP"),
)

RAW_MODEL_EXTENSIONS = {
    "sklearn": {".pkl", ".joblib"},
    "xgboost": {".xgb", ".pkl", ".joblib"},
    "pytorch": {".pt", ".pth"},
    "tensorflow": {".h5", ".keras"},
}

MAX_SOURCE_ARTIFACT_BYTES = {
    "sklearn": {
        "raw": 200 * 1024 * 1024,        # 200 MiB
        "mlflow_zip": 500 * 1024 * 1024,  # 500 MiB
    },
    "xgboost": {
        "raw": 200 * 1024 * 1024,        # 200 MiB (< 200 MB)
        "mlflow_zip": 500 * 1024 * 1024,  # 500 MiB
    },
    "pytorch": {
        "raw": 1024 * 1024 * 1024,       # 1 GiB
        "mlflow_zip": 1024 * 1024 * 1024, # 1 GiB
    },
    "tensorflow": {
        "raw": 1024 * 1024 * 1024,       # 1 GiB
        "mlflow_zip": 1024 * 1024 * 1024, # 1 GiB
    },
}


def get_max_source_artifact_bytes(flavor: str, artifact_format: str = "raw") -> int:
    flavor_limits = MAX_SOURCE_ARTIFACT_BYTES.get(flavor, {})
    return flavor_limits.get(artifact_format, 200 * 1024 * 1024)


def validate_source_artifact(*, filename: str, flavor: str, artifact_format: str, size_bytes: int | None = None) -> None:
    extension = Path(filename).suffix.lower()
    if artifact_format == "mlflow_zip":
        if extension != ".zip":
            raise ValidationError({"source_artifact": "A model package upload requires a .zip file."})
    else:
        allowed = RAW_MODEL_EXTENSIONS.get(flavor, set())
        if extension not in allowed:
            formats = ", ".join(sorted(allowed))
            raise ValidationError({"source_artifact": f"{flavor.title()} raw models require one of: {formats}."})

    if size_bytes is not None:
        if size_bytes <= 0:
            raise ValidationError({"source_artifact": "Model artifact cannot be empty."})
        max_bytes = get_max_source_artifact_bytes(flavor, artifact_format)
        if size_bytes > max_bytes:
            max_mb = max_bytes // (1024 * 1024)
            raise ValidationError(
                {"source_artifact": f"{flavor.title()} {artifact_format} artifact must be at most {max_mb} MiB."}
            )
