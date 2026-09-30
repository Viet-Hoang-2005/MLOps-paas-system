import json
import os
import pickle
from pathlib import Path
from typing import Any

import mlflow.pyfunc
from fastapi import HTTPException
from src.logging_utils import Summary, get_logger, log_event

logger = get_logger(__name__)
load_summary = Summary(logger, "model_load_summary")

MODEL_CACHE_DIR = os.environ.get("MODEL_CACHE_DIR", "/tmp/mlops_paas_models")
MODEL_CACHE: dict[str, dict[str, Any]] = {}


def _is_double_column(input_spec: Any) -> bool:
    data_type = getattr(input_spec, "type", None)
    return getattr(data_type, "name", data_type) == "double"


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


def load_label_mapping(source_dir: Path, mlflow_model_dir: Path) -> dict | None:
    """Find a mapping by filename before parsing unrelated MLflow JSON files."""
    candidates: list[Path] = []
    seen: set[Path] = set()
    for root, recursive in ((mlflow_model_dir, False), (source_dir, True)):
        files = root.rglob("*") if recursive else root.iterdir()
        for path in sorted(files):
            if path in seen or not path.is_file() or path.suffix.lower() not in {".json", ".pkl"}:
                continue
            if not any(part in path.name.lower() for part in ("mapping", "label", "dictionary")):
                continue
            seen.add(path)
            candidates.append(path)

    for path in candidates:
        try:
            with path.open("rb" if path.suffix.lower() == ".pkl" else "r") as handle:
                mapping = pickle.load(handle) if path.suffix.lower() == ".pkl" else json.load(handle)
            if isinstance(mapping, list):
                mapping = dict(enumerate(mapping))
            if isinstance(mapping, dict) and mapping:
                return mapping
        except (
            OSError,
            ValueError,
            TypeError,
            EOFError,
            ImportError,
            AttributeError,
            pickle.UnpicklingError,
        ):
            log_event(logger, "WARNING", "label_mapping_load_failed", "Label mapping could not be loaded")
    return None


def load_model_from_uri(
    model_version_id: str, model_uri: str, version_marker: str = "latest"
) -> dict[str, Any]:
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
        expected_features = (
            [inp.name for inp in signature.inputs]
            if signature and signature.inputs
            else None
        )
        float64_features = (
            [inp.name for inp in signature.inputs if _is_double_column(inp)]
            if signature and signature.inputs
            else []
        )

        label_mapping = load_label_mapping(source_dir, mlflow_model_dir)

    except Exception as exc:
        load_summary.failure(
            "load", "Model artifact load failed", error_type=type(exc).__name__
        )
        raise HTTPException(
            status_code=503, detail=f"Unable to load model artifact: {exc}"
        )

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
            if (
                hasattr(raw_model, "feature_names_in_")
                and getattr(raw_model, "feature_names_in_", None) is not None
            ):
                expected_features = list(raw_model.feature_names_in_)
            elif hasattr(raw_model, "get_booster"):
                expected_features = raw_model.get_booster().feature_names
            elif hasattr(raw_model, "feature_names"):
                expected_features = raw_model.feature_names
    except Exception as e:
        log_event(
            logger,
            "WARNING",
            "model_metadata_resolution_failed",
            "Model compatibility metadata could not be resolved",
            error_type=type(e).__name__,
        )

    MODEL_CACHE[model_version_id] = {
        "model": pyfunc_model,
        "expected_features": expected_features,
        "float64_features": float64_features,
        "label_mapping": label_mapping,
        "version_marker": version_marker,
    }
    load_summary.recovery("load")
    log_event(logger, "INFO", "model_loaded", "Model artifact loaded")
    return MODEL_CACHE[model_version_id]


def load_model_for_record(model_record: dict[str, Any]) -> dict[str, Any]:
    model_version_id = str(model_record["id"])
    model_uri = model_record.get("model_uri")
    version_marker = str(model_record.get("updated_at", "latest"))
    return load_model_from_uri(model_version_id, model_uri, version_marker)
