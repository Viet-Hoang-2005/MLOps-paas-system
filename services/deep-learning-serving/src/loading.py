import os
from pathlib import Path

MODEL_CACHE_DIR = os.environ.get("MODEL_CACHE_DIR", "/tmp/mlops_paas_models")

def download_model_artifact(model_version_id: str, model_uri: str) -> Path:
    prebuilt_dir = Path("/app/model_artifact")
    if prebuilt_dir.exists() and any(prebuilt_dir.iterdir()):
        if (prebuilt_dir / "source").exists():
            return prebuilt_dir / "source"
        return prebuilt_dir

    if model_uri:
        local_path = Path(model_uri)
        if local_path.exists() and local_path.is_dir():
            return local_path

    raise RuntimeError(
        f"FATAL: Pre-built DL model artifact not found in /app/model_artifact "
        f"(Model Version ID: {model_version_id}). "
    )

def resolve_mlflow_model_dir(source_dir: Path) -> Path:
    root_mlmodel = source_dir / "MLmodel"
    if root_mlmodel.exists():
        return source_dir

    candidates = list(source_dir.rglob("MLmodel"))
    if not candidates:
        raise FileNotFoundError("MLmodel file was not found in the model artifact.")
    return candidates[0].parent
