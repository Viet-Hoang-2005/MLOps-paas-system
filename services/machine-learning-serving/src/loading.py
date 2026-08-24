import os
import json
import pickle
import mlflow.pyfunc
from pathlib import Path
from typing import Any, Dict
from fastapi import HTTPException

MODEL_CACHE_DIR = os.environ.get("MODEL_CACHE_DIR", "/tmp/mlops_paas_models")
MODEL_CACHE: Dict[str, Dict[str, Any]] = {}

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
        f"FATAL: Pre-built model artifact not found in /app/model_artifact (Model Version ID: {model_version_id}). "
    )

def resolve_mlflow_model_dir(source_dir: Path) -> Path:
    root_mlmodel = source_dir / "MLmodel"
    if root_mlmodel.exists():
        return source_dir

    candidates = list(source_dir.rglob("MLmodel"))
    if not candidates:
        raise FileNotFoundError("MLmodel file was not found in the model artifact.")
    return candidates[0].parent

def load_model_from_uri(model_version_id: str, model_uri: str, version_marker: str = "latest") -> Dict[str, Any]:
    cached = MODEL_CACHE.get(model_version_id)
    if cached and cached.get("version_marker") == version_marker:
        return cached

    if not model_uri:
        raise HTTPException(status_code=503, detail="Model artifact URI is empty.")

    try:
        source_dir = download_model_artifact(model_version_id, model_uri)
        mlflow_model_dir = resolve_mlflow_model_dir(source_dir)
        pyfunc_model = mlflow.pyfunc.load_model(str(mlflow_model_dir))
        signature = pyfunc_model.metadata.signature
        expected_features = [inp.name for inp in signature.inputs] if signature and signature.inputs else None

        label_mapping = None
        for ext, loader, mode in [(".json", json.load, "r"), (".pkl", pickle.load, "rb")]:
            mapping_file = next(mlflow_model_dir.glob(f"*{ext}"), None)
            if mapping_file and ("mapping" in mapping_file.name.lower() or "label" in mapping_file.name.lower() or "dictionary" in mapping_file.name.lower()):
                try:
                    with mapping_file.open(mode) as f:
                        label_mapping = loader(f)
                        if isinstance(label_mapping, list):
                            label_mapping = {i: v for i, v in enumerate(label_mapping)}
                    break
                except Exception as e:
                    print(f"Failed to load mapping file {mapping_file}: {e}")

        if not label_mapping:
            for ext, loader, mode in [(".json", json.load, "r"), (".pkl", pickle.load, "rb")]:
                mapping_file = next(source_dir.rglob(f"*{ext}"), None)
                if mapping_file and ("mapping" in mapping_file.name.lower() or "label" in mapping_file.name.lower() or "dictionary" in mapping_file.name.lower()):
                    try:
                        with mapping_file.open(mode) as f:
                            label_mapping = loader(f)
                            if isinstance(label_mapping, list):
                                label_mapping = {i: v for i, v in enumerate(label_mapping)}
                        break
                    except Exception:
                        pass

    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to load model artifact: {exc}")

    try:
        raw_model = None
        if hasattr(pyfunc_model, "unwrap_python_model"):
            try:
                raw_model = pyfunc_model.unwrap_python_model()
            except Exception:
                pass
        if not raw_model and hasattr(pyfunc_model, "_model_impl"):
            raw_model = getattr(pyfunc_model._model_impl, "xgb_model", None)
            
        if raw_model and type(raw_model).__name__ == "XGBClassifier":
            if not hasattr(raw_model, "n_classes_"):
                if label_mapping:
                    raw_model.n_classes_ = len(label_mapping)
                else:
                    raw_model.n_classes_ = len(getattr(raw_model, "classes_", [0, 1]))
                
        if not expected_features and raw_model:
            if hasattr(raw_model, "feature_names_in_") and getattr(raw_model, "feature_names_in_", None) is not None:
                expected_features = list(raw_model.feature_names_in_)
            elif hasattr(raw_model, "get_booster"):
                expected_features = raw_model.get_booster().feature_names
            elif hasattr(raw_model, "feature_names"):
                expected_features = raw_model.feature_names
    except Exception as e:
        print(f"Failed to apply XGBClassifier workaround or extract feature names: {e}")

    MODEL_CACHE[model_version_id] = {
        "model": pyfunc_model,
        "expected_features": expected_features,
        "label_mapping": label_mapping,
        "version_marker": version_marker,
    }
    return MODEL_CACHE[model_version_id]

def load_model_for_record(model_record: Dict[str, Any]) -> Dict[str, Any]:
    model_version_id = str(model_record["id"])
    model_uri = model_record.get("model_uri")
    version_marker = str(model_record.get("updated_at", "latest"))
    return load_model_from_uri(model_version_id, model_uri, version_marker)
