import pickle
import zipfile
from pathlib import Path
from typing import Any

import cloudpickle
import joblib
from src.image_build import normalize_mlflow_requirements


def parse_requirements(requirements_text: str) -> list[str] | None:
    requirements = [
        line.strip() for line in requirements_text.splitlines() if line.strip() and not line.strip().startswith("#")
    ]
    return requirements or None


def _apply_sklearn_compatibility_shims() -> None:
    """Ensure older scikit-learn artifacts (<= 1.6.1) can be unpickled in >= 1.7.0."""
    try:
        import sklearn.compose._column_transformer as _ct

        if not hasattr(_ct, "_RemainderColsList"):
            class _RemainderColsList(list):
                pass

            _ct._RemainderColsList = _RemainderColsList
    except Exception:
        pass


def _sanitize_sklearn_model(model: Any) -> Any:
    """Normalize internal objects to standard Python types for forward compatibility."""
    try:
        from sklearn.pipeline import Pipeline
        from sklearn.compose import ColumnTransformer

        transformers = []
        if isinstance(model, Pipeline):
            for _, step in model.steps:
                if isinstance(step, ColumnTransformer):
                    transformers.append(step)
        elif isinstance(model, ColumnTransformer):
            transformers.append(model)

        for ct in transformers:
            if hasattr(ct, "_remainder") and isinstance(ct._remainder, tuple) and len(ct._remainder) == 3:
                ct._remainder = (ct._remainder[0], ct._remainder[1], list(ct._remainder[2]))
    except Exception:
        pass
    return model


def load_pickle_model(path: Path) -> Any:
    _apply_sklearn_compatibility_shims()

    extension = path.suffix.lower()
    loaders = (
        ("joblib", lambda item: joblib.load(item)),
        ("cloudpickle", lambda item: cloudpickle.load(item.open("rb"))),
        ("pickle", lambda item: pickle.load(item.open("rb"))),
    )

    errors: list[str] = []
    joblib_exc: Exception | None = None
    for name, loader in loaders:
        try:
            model = loader(path)
            return _sanitize_sklearn_model(model)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            if name == "joblib" and joblib_exc is None:
                joblib_exc = exc

    if extension == ".joblib" and joblib_exc is not None:
        raise ValueError(f"Unable to load model artifact: {joblib_exc}")

    raise ValueError(f"Unable to load model artifact: {errors[-1] if errors else 'unknown error'}")


def load_model(path: Path, flavor: str) -> Any:
    extension = path.suffix.lower()

    if flavor == "sklearn":
        if extension not in {".pkl", ".joblib"}:
            raise ValueError("Scikit-learn flavor requires a .pkl or .joblib artifact.")
        return load_pickle_model(path)

    if flavor == "xgboost":
        if extension == ".xgb":
            import xgboost as xgb

            booster = xgb.Booster()
            booster.load_model(str(path))
            return booster
        if extension in {".pkl", ".joblib"}:
            return load_pickle_model(path)
        raise ValueError("XGBoost flavor requires a .xgb, .pkl, or .joblib artifact.")

    if flavor == "pytorch":
        if extension not in {".pth", ".pt"}:
            raise ValueError("PyTorch flavor requires a .pth or .pt artifact.")
        import torch

        return torch.load(path, map_location="cpu")

    if flavor in {"tensorflow", "keras"}:
        if extension not in {".h5", ".keras"}:
            raise ValueError("Keras flavor requires a .h5 or .keras artifact.")
        try:
            import tensorflow as tf

            return tf.keras.models.load_model(path)
        except ImportError:
            import keras

            return keras.models.load_model(path)

    raise ValueError(f"Unsupported model flavor: {flavor}")


def save_mlflow_model(model: Any, flavor: str, output_dir: Path, requirements: list[str] | None) -> None:
    platform_requirements = normalize_mlflow_requirements(requirements)
    if flavor == "sklearn":
        import mlflow.sklearn

        mlflow.sklearn.save_model(
            sk_model=model,
            path=str(output_dir),
            pip_requirements=platform_requirements,
            serialization_format="cloudpickle",
        )
        return

    if flavor == "xgboost":
        import mlflow.xgboost

        mlflow.xgboost.save_model(
            xgb_model=model,
            path=str(output_dir),
            pip_requirements=platform_requirements,
        )
        return

    if flavor == "pytorch":
        import mlflow.pytorch

        mlflow.pytorch.save_model(
            pytorch_model=model,
            path=str(output_dir),
            pip_requirements=platform_requirements,
            serialization_format="pickle",
        )
        return

    if flavor in {"tensorflow", "keras"}:
        import mlflow.keras

        try:
            mlflow.keras.save_model(
                keras_model=model,
                path=str(output_dir),
                pip_requirements=platform_requirements,
            )
        except AttributeError:
            import mlflow.tensorflow

            mlflow.tensorflow.save_model(
                model=model,
                path=str(output_dir),
                pip_requirements=platform_requirements,
            )
        return

    raise ValueError(f"Unsupported model flavor: {flavor}")


def build_preview_tree(root: Path) -> list[str]:
    paths: list[str] = []
    for item in sorted(root.rglob("*")):
        relative = item.relative_to(root.parent).as_posix()
        paths.append(f"{relative}/" if item.is_dir() else relative)
    return paths


def make_zip(source_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in source_dir.rglob("*"):
            archive.write(item, item.relative_to(source_dir.parent))
