import pickle
import zipfile
import joblib
import cloudpickle

import mlflow.sklearn
import mlflow.xgboost
import mlflow.pytorch
import mlflow.keras
import mlflow.tensorflow

import torch
import xgboost as xgb
import tensorflow as tf
import keras

from pathlib import Path
from typing import Any

def parse_requirements(requirements_text: str) -> list[str] | None:
    requirements = [
        line.strip()
        for line in requirements_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return requirements or None

def load_pickle_model(path: Path) -> Any:
    loaders = (
        lambda item: joblib.load(item),
        lambda item: cloudpickle.load(item.open("rb")),
        lambda item: pickle.load(item.open("rb")),
    )

    last_error: Exception | None = None
    for loader in loaders:
        try:
            return loader(path)
        except Exception as exc:
            last_error = exc

    raise ValueError(f"Unable to load model artifact: {last_error}")

def load_model(path: Path, flavor: str) -> Any:
    extension = path.suffix.lower()

    if flavor == "sklearn":
        if extension not in {".pkl", ".joblib"}:
            raise ValueError("Scikit-learn flavor requires a .pkl or .joblib artifact.")
        return load_pickle_model(path)

    if flavor == "xgboost":
        if extension == ".xgb":
            booster = xgb.Booster()
            booster.load_model(str(path))
            return booster
        if extension in {".pkl", ".joblib"}:
            return load_pickle_model(path)
        raise ValueError("XGBoost flavor requires a .xgb, .pkl, or .joblib artifact.")

    if flavor == "pytorch":
        if extension not in {".pth", ".pt"}:
            raise ValueError("PyTorch flavor requires a .pth or .pt artifact.")
        return torch.load(path, map_location="cpu")

    if flavor in {"tensorflow", "keras"}:
        if extension not in {".h5", ".keras"}:
            raise ValueError("Keras flavor requires a .h5 or .keras artifact.")
        try:
            return tf.keras.models.load_model(path)
        except ImportError:
            return keras.models.load_model(path)

    raise ValueError(f"Unsupported model flavor: {flavor}")

def save_mlflow_model(model: Any, flavor: str, output_dir: Path, requirements: list[str] | None) -> None:
    if flavor == "sklearn":
        mlflow.sklearn.save_model(
            sk_model=model,
            path=str(output_dir),
            pip_requirements=requirements,
        )
        return

    if flavor == "xgboost":
        mlflow.xgboost.save_model(
            xgb_model=model,
            path=str(output_dir),
            pip_requirements=requirements,
        )
        return

    if flavor == "pytorch":
        mlflow.pytorch.save_model(
            pytorch_model=model,
            path=str(output_dir),
            pip_requirements=requirements,
        )
        return

    if flavor in {"tensorflow", "keras"}:
        try:
            mlflow.keras.save_model(
                keras_model=model,
                path=str(output_dir),
                pip_requirements=requirements,
            )
        except AttributeError:
            mlflow.tensorflow.save_model(
                model=model,
                path=str(output_dir),
                pip_requirements=requirements,
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
