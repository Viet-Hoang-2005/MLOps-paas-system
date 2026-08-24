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


def validate_source_artifact(*, filename, flavor, artifact_format):
    extension = Path(filename).suffix.lower()
    if artifact_format == "mlflow_zip":
        if extension != ".zip":
            raise ValidationError({"source_artifact": "A model package upload requires a .zip file."})
        return

    allowed = RAW_MODEL_EXTENSIONS[flavor]
    if extension not in allowed:
        formats = ", ".join(sorted(allowed))
        raise ValidationError(
            {"source_artifact": f"{flavor.title()} raw models require one of: {formats}."}
        )
